import json
from types import SimpleNamespace

import httpx
import pytest
from zhixing_connectors.catalog import official_raw_spec
from zhixing_connectors.official_contracts import official_contracts
from zhixing_jobs import PermanentJobError

from zhixing_worker.config import WorkerSettings
from zhixing_worker.main import (
    _execute_lingxing_sync,
    order_store_filter,
    resolve_order_store_filter,
    resolve_store_scope_parameter,
    warehouse_scope_filter,
)


def test_selected_project_orders_restrict_official_sid_list():
    scope = {'scope_level':'business_unit','store_ids':['store:12','store:2']}
    assert order_store_filter(scope, {'store:12':'12','store:2':'2'}) == [2,12]
    assert order_store_filter({'scope_level':'enterprise','store_ids':[]}) is None


def test_store_scope_resolution_never_crosses_provider_namespace():
    scope = {'scope_level':'business_unit','store_ids':['amazon','multi']}
    mapping = {'amazon':'12', 'multi':'multiplatform:34'}
    assert order_store_filter(scope, mapping, namespace='amazon') == [12]
    assert order_store_filter(scope, mapping, namespace='multiplatform') == [34]
    with pytest.raises(PermanentJobError):
        order_store_filter({'scope_level':'store','store_ids':['amazon']}, mapping,
                           namespace='multiplatform')


def test_project_bound_source_requires_assigned_store_and_warehouse_scope():
    with pytest.raises(PermanentJobError) as store_error:
        order_store_filter({'scope_level':'enterprise','store_ids':[]}, {}, required=True)
    assert store_error.value.code == 'sync.store_partition_required'
    assert warehouse_scope_filter({'scope_level':'enterprise','warehouse_ids':['opaque']},
                                  {'opaque':'71'}, required=True) == [71]
    with pytest.raises(PermanentJobError) as warehouse_error:
        warehouse_scope_filter({'scope_level':'enterprise','warehouse_ids':[]}, {}, required=True)
    assert warehouse_error.value.code == 'sync.warehouse_partition_required'

@pytest.mark.parametrize('stores', [[], ['not-a-store'], ['store:0'], ['store:-1'],
    [f'store:{i}' for i in range(1,22)]])
def test_selected_order_scope_never_falls_back_to_all_account(stores):
    with pytest.raises(PermanentJobError):
        order_store_filter({'scope_level':'store','store_ids':stores},
                           {key:key.removeprefix('store:') for key in stores})


@pytest.mark.parametrize('response_sid', [2, 99])
@pytest.mark.parametrize('resource', ['orders', 'after_sales', 'listings', 'fulfillments'])
def test_order_request_scope_and_archive_fence(tmp_path, response_sid, monkeypatch, resource):
    def resolve(snapshot, engine, enterprise_id, source_key):
        assert source_key == 'synthetic-source'
        return [2]
    monkeypatch.setattr('zhixing_worker.main.resolve_order_store_filter', resolve)
    calls = []
    def respond(request):
        if request.url.path.endswith('access-token'):
            return httpx.Response(200, json={'code':200, 'data':{
                'access_token':'synthetic-only', 'refresh_token':'synthetic-refresh',
                'expires_in':3600}})
        body = json.loads(request.content)
        if resource == 'orders':
            assert body['sid_list'] == [2]
        elif resource == 'fulfillments':
            assert body['sid_arr'] == [2] and 'sid' not in body
        else:
            assert body['sid'] == '2' and 'sid_list' not in body
        if resource == 'after_sales':
            assert body['start_date'] == '2026-09-01'
            assert body['end_date'] == '2026-09-02'
        calls.append(body)
        return httpx.Response(200, json={'code':0,'total':1,'data':[{'sid':response_sid}]})
    job = SimpleNamespace(enterprise_id='legal', payload={'provider':'lingxing',
        'resource_key':resource,'source_id':'synthetic-source',
        'resource_parameters':({'sid':'2','is_delete':'0'} if resource == 'listings' else
                               {}),
        'scope_snapshot':{'scope_level':'store','store_ids':['store:2']},
        **({'window_start':'2026-09-01T00:00:00+00:00',
            'window_end':'2026-09-02T00:00:00+00:00'}
           if resource in {'orders', 'after_sales', 'fulfillments'} else {})})
    context = SimpleNamespace(ensure_active=lambda:None)
    settings = WorkerSettings('sqlite://', 'verify', 1, 60, 1, 0,
        lingxing_app_id='synthetic-app-16',lingxing_app_secret='synthetic-only',
        lingxing_enabled=True,source_archive_path=str(tmp_path))
    if response_sid == 99:
        with pytest.raises(PermanentJobError) as error:
            _execute_lingxing_sync(job, context, settings, transport=httpx.MockTransport(respond))
        assert error.value.code == 'sync.response_scope_mismatch'
        assert not list(tmp_path.rglob('*.gz'))
    else:
        _execute_lingxing_sync(job, context, settings, transport=httpx.MockTransport(respond))
        assert list(tmp_path.rglob('*.gz'))
    assert len(calls) == 1


def test_store_resolution_uses_source_origin_and_rejects_unassigned_or_other_source():
    from sqlalchemy import create_engine, text
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE business_entities (id TEXT, enterprise_id TEXT, '
                          'canonical_key TEXT, entity_type TEXT)'))
        conn.execute(text('CREATE TABLE external_systems (id TEXT, enterprise_id TEXT, '
                          'system_key TEXT, business_unit_id TEXT)'))
        conn.execute(text('CREATE TABLE canonical_entity_origins (entity_id TEXT, '
            'enterprise_id TEXT, external_system_id TEXT, external_key TEXT, '
            'resource_key TEXT, status TEXT, business_unit_id TEXT)'))
        conn.execute(text("INSERT INTO external_systems VALUES "
                          "('s1','legal','source',NULL),('s2','legal','other',NULL)"))
        for key, source, status in [('opaque-a','s1','assigned'),
                                    ('opaque-b','s2','assigned'),('opaque-c','s1','unassigned')]:
            conn.execute(text("INSERT INTO business_entities VALUES (:key,:legal,:key,'store')"),
                         {'key':key,'legal':'legal'})
            conn.execute(text('INSERT INTO canonical_entity_origins VALUES '
                "(:key,'legal',:source,'12','shops',:status,NULL)"),
                {'key':key,'source':source,'status':status})
    scope = {'scope_level':'business_unit','store_ids':['opaque-a']}
    assert resolve_order_store_filter(scope, engine, 'legal', 'source') == [12]
    for key in ['opaque-b','opaque-c']:
        with pytest.raises(PermanentJobError):
            resolve_order_store_filter({**scope,'store_ids':[key]},engine,'legal','source')
    with pytest.raises(PermanentJobError):
        resolve_order_store_filter(scope,engine,'other-legal','source')
    engine.dispose()


def test_seller_id_scope_resolves_only_from_approved_store_dependencies():
    from sqlalchemy import create_engine, text
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE source_request_budgets '
                          '(id TEXT PRIMARY KEY, next_allowed_epoch NUMERIC NOT NULL, '
                          'updated_at DATETIME NOT NULL)'))
        conn.execute(text('CREATE TABLE external_systems '
                          '(id TEXT, enterprise_id TEXT, system_key TEXT, business_unit_id TEXT)'))
        conn.execute(text('CREATE TABLE source_dependency_values '
                          '(enterprise_id TEXT, external_system_id TEXT, value_type TEXT, '
                          'external_value TEXT, scope_kind TEXT, scope_external_key TEXT, '
                          'status TEXT, business_unit_id TEXT)'))
        conn.execute(text("INSERT INTO external_systems VALUES "
                          "('s1','legal','source','bu')"))
        conn.execute(text("INSERT INTO source_dependency_values VALUES "
                          "('legal','s1','seller_id','SELLER-X','store','store:23','active','bu'),"
                          "('legal','s1','seller_id','SELLER-Y','store','store:99','active','bu')"))
    assert resolve_store_scope_parameter(
        [23], engine, 'legal', 'source', 'seller_id') == ['SELLER-X']
    with pytest.raises(PermanentJobError) as missing:
        resolve_store_scope_parameter([24], engine, 'legal', 'source', 'seller_id')
    assert missing.value.code == 'sync.contract_scope_mapping_missing'
    engine.dispose()


def test_virtual_numeric_seller_scope_is_mapped_before_provider_request(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, text
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE source_request_budgets '
                          '(id TEXT PRIMARY KEY, next_allowed_epoch NUMERIC NOT NULL, '
                          'updated_at DATETIME NOT NULL)'))
        conn.execute(text('CREATE TABLE external_systems '
                          '(id TEXT, enterprise_id TEXT, system_key TEXT, business_unit_id TEXT)'))
        conn.execute(text('CREATE TABLE source_dependency_values '
                          '(enterprise_id TEXT, external_system_id TEXT, value_type TEXT, '
                          'external_value TEXT, scope_kind TEXT, scope_external_key TEXT, '
                          'status TEXT, business_unit_id TEXT)'))
        conn.execute(text("INSERT INTO external_systems VALUES "
                          "('s1','legal','source','bu')"))
        conn.execute(text("INSERT INTO source_dependency_values VALUES "
                          "('legal','s1','seller_id','SELLER-X','store','store:23','active','bu')"))
    monkeypatch.setattr('zhixing_worker.main.resolve_order_store_filter',
                        lambda *args: [23])
    calls = []

    def respond(request):
        if request.url.path.endswith('access-token'):
            return httpx.Response(200, json={'code': 200, 'data': {
                'access_token': 'synthetic-only', 'refresh_token': 'synthetic-refresh',
                'expires_in': 3600,
            }})
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json={'code': 0, 'data': {
            'row_data': [], 'total': 0,
        }})

    settings = WorkerSettings('sqlite://', 'verify', 1, 60, 1, 0,
                              lingxing_app_id='synthetic-app-16',
                              lingxing_app_secret='synthetic-only',
                              lingxing_enabled=True, source_archive_path=str(tmp_path))
    _execute_lingxing_sync(SimpleNamespace(enterprise_id='legal', payload={
        'provider': 'lingxing', 'resource_key': 'official_72791537e588ec5e',
        'source_id': 'source', 'resource_parameters': {'seller_id': '23'},
        'scope_snapshot': {'scope_level': 'business_unit', 'store_ids': ['store:23']},
        'window_start': '2026-08-01T00:00:00+00:00',
        'window_end': '2026-08-02T00:00:00+00:00',
    }), SimpleNamespace(ensure_active=lambda: None), settings,
        budget_engine=engine, transport=httpx.MockTransport(respond))
    assert calls[0]['seller_id'] == ['SELLER-X']
    engine.dispose()


@pytest.mark.parametrize('resource,parameters,response_data,expected_key,expected_value', [
    ('fbm_orders', {'sid':'2'}, [{'order_number':'SYNTHETIC'}], 'sid', '2'),
    ('fba_shipments', {}, {'list':[{'id':1, 'relate_list':[{'sid':2}]}], 'total':1},
     'sids', '2,12'),
    ('fba_inventory', {}, [{'sid':2, 'seller_sku':'SYNTHETIC'}], 'sid', '2,12'),
    ('advertising', {'sid':'2'}, [{'campaign_id':1}], 'sid', 2),
    ('finance', {'sid':'2'}, {'records':[{'id':1}], 'total':1}, 'sids', [2]),
    ('customer_service', {'sid':'2'}, [{'review_id':'SYNTHETIC'}], 'sids', '2'),
    ('source_reports', {'sid':'2'}, [{'sid':2, 'amazon_order_id':'SYNTHETIC'}], 'sid', 2),
])
def test_remaining_store_resources_apply_project_scope(
    tmp_path, monkeypatch, resource, parameters, response_data, expected_key, expected_value,
):
    monkeypatch.setattr('zhixing_worker.main.resolve_order_store_filter',
                        lambda *args: [2, 12])
    calls = []
    def respond(request):
        if request.url.path.endswith('access-token'):
            return httpx.Response(200, json={'code':200, 'data':{
                'access_token':'synthetic-only', 'refresh_token':'synthetic-refresh',
                'expires_in':3600}})
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json={'code':0, 'total':1, 'data':response_data})
    window = ({'window_start':'2026-09-01T00:00:00+00:00',
               'window_end':'2026-09-02T00:00:00+00:00'}
              if resource not in {'fba_inventory', 'advertising'} else {})
    settings = WorkerSettings('sqlite://', 'verify', 1, 60, 1, 0,
        lingxing_app_id='synthetic-app-16', lingxing_app_secret='synthetic-only',
        lingxing_enabled=True, source_archive_path=str(tmp_path))
    _execute_lingxing_sync(SimpleNamespace(enterprise_id='legal', payload={
        'provider':'lingxing', 'resource_key':resource, 'source_id':'synthetic-source',
        'resource_parameters':parameters,
        'scope_snapshot':{'scope_level':'business_unit','store_ids':['opaque']}, **window,
    }), SimpleNamespace(ensure_active=lambda:None), settings,
        transport=httpx.MockTransport(respond))
    assert calls[0][expected_key] == expected_value


@pytest.mark.parametrize('resource,expected_key', [
    ('warehouse_bins', 'wid'), ('inventory', 'wid'), ('inventory_statements', 'wids'),
])
def test_warehouse_resources_apply_project_scope(
    tmp_path, monkeypatch, resource, expected_key,
):
    monkeypatch.setattr('zhixing_worker.main.resolve_warehouse_filter',
                        lambda *args: [71, 72])
    calls = []
    def respond(request):
        if request.url.path.endswith('access-token'):
            return httpx.Response(200, json={'code':200, 'data':{
                'access_token':'synthetic-only', 'refresh_token':'synthetic-refresh',
                'expires_in':3600}})
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json={'code':0, 'total':1,
                                         'data':[{'wid':71, 'id':1}]})
    window = ({'window_start':'2026-09-01T00:00:00+00:00',
               'window_end':'2026-09-02T00:00:00+00:00'}
              if resource == 'inventory_statements' else {})
    settings = WorkerSettings('sqlite://', 'verify', 1, 60, 1, 0,
        lingxing_app_id='synthetic-app-16', lingxing_app_secret='synthetic-only',
        lingxing_enabled=True, source_archive_path=str(tmp_path))
    _execute_lingxing_sync(SimpleNamespace(enterprise_id='legal', payload={
        'provider':'lingxing', 'resource_key':resource, 'source_id':'synthetic-source',
        'resource_parameters':{},
        'scope_snapshot':{'scope_level':'business_unit','warehouse_ids':['opaque']}, **window,
    }), SimpleNamespace(ensure_active=lambda:None), settings,
        transport=httpx.MockTransport(respond))
    assert calls[0][expected_key] == '71,72'


def test_single_warehouse_endpoint_requires_one_partition(tmp_path, monkeypatch):
    monkeypatch.setattr('zhixing_worker.main.resolve_warehouse_filter',
                        lambda *args: [71, 72])
    settings = WorkerSettings('sqlite://', 'verify', 1, 60, 1, 0,
        lingxing_app_id='synthetic-app-16', lingxing_app_secret='synthetic-only',
        lingxing_enabled=True, source_archive_path=str(tmp_path))
    with pytest.raises(PermanentJobError) as error:
        _execute_lingxing_sync(SimpleNamespace(enterprise_id='legal', payload={
            'provider':'lingxing', 'resource_key':'inbound_orders',
            'source_id':'synthetic-source', 'resource_parameters':{},
            'scope_snapshot':{'scope_level':'business_unit','warehouse_ids':['a','b']},
            'window_start':'2026-09-01T00:00:00+00:00',
            'window_end':'2026-09-02T00:00:00+00:00',
        }), SimpleNamespace(ensure_active=lambda:None), settings)
    assert error.value.code == 'sync.warehouse_single_partition_required'


def test_official_raw_profile_is_fenced_to_approved_store_before_request(tmp_path, monkeypatch):
    contract = next(item for item in official_contracts()
                    if item.path == '/erp/sc/data/mws_report/dailyInventory')
    spec = official_raw_spec(contract.id)
    assert spec is not None
    monkeypatch.setattr('zhixing_worker.main.resolve_order_store_filter',
                        lambda *args: [23])
    calls = []

    def respond(request):
        if request.url.path.endswith('access-token'):
            return httpx.Response(200, json={'code': 200, 'data': {
                'access_token': 'synthetic', 'refresh_token': 'synthetic',
                'expires_in': 3600}})
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json={'code': 0, 'data': [
            {'snapshot_date': '2026-01-01T00:00:00+00:00', 'sku': 'SYNTHETIC',
             'quantity': 1}]})

    settings = WorkerSettings('sqlite://', 'verify', 1, 60, 1, 0,
        lingxing_app_id='synthetic-app-16', lingxing_app_secret='synthetic-only',
        lingxing_enabled=True, source_archive_path=str(tmp_path))
    result = _execute_lingxing_sync(SimpleNamespace(enterprise_id='legal', payload={
        'provider': 'lingxing', 'resource_key': spec.key, 'source_id': 'synthetic-source',
        'resource_parameters': {'sid': '23', 'event_date': '2026-01-01'},
        'scope_snapshot': {'scope_level': 'business_unit', 'store_ids': ['opaque']},
    }), SimpleNamespace(ensure_active=lambda: None), settings,
        transport=httpx.MockTransport(respond))
    assert calls == [{'sid': 23, 'event_date': '2026-01-01', 'offset': 0, 'length': 20}]
    assert result['row_count'] == 1

    calls.clear()
    with pytest.raises(PermanentJobError) as error:
        _execute_lingxing_sync(SimpleNamespace(enterprise_id='legal', payload={
            'provider': 'lingxing', 'resource_key': spec.key,
            'source_id': 'synthetic-source',
            'resource_parameters': {'sid': '99', 'event_date': '2026-01-01'},
            'scope_snapshot': {'scope_level': 'business_unit', 'store_ids': ['opaque']},
        }), SimpleNamespace(ensure_active=lambda: None), settings,
            transport=httpx.MockTransport(respond))
    assert error.value.code == 'sync.contract_scope_invalid' and calls == []
