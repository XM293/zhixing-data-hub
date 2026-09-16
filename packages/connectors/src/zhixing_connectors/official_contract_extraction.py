from __future__ import annotations

import re
from typing import TypedDict


class ContractField(TypedDict):
    path: list[str]
    name: str
    required: bool
    type: str
    description: str


class ExtractedContract(TypedDict):
    request_fields: list[ContractField]
    response_fields: list[ContractField]
    required_fields: list[str]
    scope_fields: list[str]
    pagination_mode: str
    window_fields: list[str]
    window_format: str
    rows_path: list[str]
    total_path: list[str]
    rate_capacity: int | None
    max_window_days: int | None
    retention_days: int | None
    extraction_status: str


_SCOPE_NAMES = frozenset({
    "sid", "sids", "sidlist", "sellerid", "sellerids", "storeid", "storeids",
    "shopid", "shopids", "wid", "wids", "widlist", "warehouseid", "warehouseids",
    "countrycode", "region", "marketplaceid",
})
_WINDOW_NAMES = frozenset({
    "startdate", "enddate", "starttime", "endtime", "begindate", "finishdate",
    "begintime", "finishtime", "eventdate", "snapshotdate", "reportdate",
    "settlementdate", "date",
})


def _normalized_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _is_window_field(value: str) -> bool:
    normalized = _normalized_name(value)
    return (normalized in _WINDOW_NAMES
            or (any(token in normalized for token in ("date", "time"))
                and any(token in normalized for token in (
                    "start", "begin", "after", "end", "finish", "before"))))


def _plain(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", value)
    return value.replace("`", "").replace("**", "").strip()


def _cells(line: str) -> list[str]:
    return [_plain(value) for value in line.strip().strip("|").split("|")]


def _section(lines: list[str], names: tuple[str, ...]) -> tuple[list[str], bool]:
    start = next((index + 1 for index, line in enumerate(lines)
                  if any(re.sub(r"^[#\s]+|[#：:\s]+$", "", _plain(line)).lower().startswith(name)
                         for name in names)), None)
    if start is None:
        return [], False
    end = next((index for index in range(start, len(lines))
                if lines[index].startswith("## ")), len(lines))
    return lines[start:end], True


def _fields(lines: list[str]) -> list[ContractField]:
    result: list[ContractField] = []
    for line in lines:
        if not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if len(cells) < 4 or not cells[0] or cells[0] in {"参数名", "字段名", "参数"}:
            continue
        if set(cells[0]) <= {":", "-", " "}:
            continue
        raw_name = cells[0].replace("→", ">>").replace("&gt;", ">")
        path = [_plain(part).strip("[] ") for part in raw_name.split(">>") if _plain(part)]
        if not path or any(not part for part in path):
            continue
        type_name = _plain(cells[3]).strip("[] ").lower() or "unknown"
        required_value = cells[2].lower().replace(" ", "")
        result.append({
            "path": path,
            "name": path[-1],
            "required": required_value in {"是", "必填", "yes", "y", "true"},
            "type": type_name,
            "description": cells[1],
        })
    return result


def _pagination(names: set[str]) -> str:
    lowered = {_normalized_name(name) for name in names}
    if {"offset", "length"} <= lowered:
        return "offset_length"
    if {"offset", "limit"} <= lowered:
        return "offset_limit"
    if lowered.intersection({"page", "pageno", "pagenum", "current"}) and lowered.intersection(
        {"pagesize", "length", "size"}
    ):
        return "page"
    if lowered.intersection({"offset", "page", "current", "pageno", "pagenum"}):
        return "unknown"
    return "none"


def _response_paths(fields: list[ContractField]) -> tuple[list[str], list[str]]:
    def is_collection(field: ContractField) -> bool:
        marker = f'{field["type"]} {field["description"]}'.lower()
        return "array" in marker or "list" in marker

    arrays = [field["path"] for field in fields
              if is_collection(field) and field["path"][0].lower() == "data"]
    nested = [field["path"] for field in fields if len(field["path"]) > 1
              and field["path"][0].lower() == "data"
              and _normalized_name(field["path"][-1]) in {
                  "data", "items", "list", "records", "results", "rows",
              }
              and (is_collection(field) or any(
                  other["path"][:len(field["path"])] == field["path"]
                  and len(other["path"]) > len(field["path"])
                  for other in fields))]
    outer = next((field for field in fields if field["path"] == ["data"]), None)
    outer_is_explicit_list = bool(outer and is_collection(outer)
        and any(token in outer["description"].lower()
                for token in ("列表", "集合", " list", "array")))
    # Official tables often label the outer data wrapper as an array even when a nested
    # list/records field is the actual row collection. A descriptive outer list remains rows.
    choices = arrays if outer_is_explicit_list else nested or arrays
    rows = min(choices, key=len) if choices else []
    totals = [field["path"] for field in fields
              if field["name"].lower() in {"total", "total_count", "totalcount", "count"}
              and len(field["path"]) <= 3]
    siblings = [path for path in totals if rows and path[:-1] == rows[:-1]]
    total = min(siblings or totals, key=len) if siblings or totals else []
    return rows, total


def _interface(document: str, path: str, method: str) -> tuple[bool, int | None]:
    for line in document.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if len(cells) < 3:
            continue
        normalized_path = cells[0].strip()
        normalized_method = cells[2].strip().upper()
        if normalized_path.rstrip() != path.rstrip() or normalized_method != method.upper():
            continue
        capacity = next((int(value) for value in reversed(cells[3:])
                         if re.fullmatch(r"[1-9][0-9]*", value)), None)
        return True, capacity
    return False, None


def _window_limits(fields: list[ContractField], window: list[str]) -> tuple[int | None, int | None]:
    descriptions = " ".join(field["description"] for field in fields
                            if field["name"] in window)
    maximums = [int(value) for value in re.findall(
        r"(?:最大跨度|最长(?:不得|不)?超过|范围(?:不得|不能|不)?超过|最多支持|"
        r"(?:开始结束时间)?区间支持)\s*(\d+)\s*天",
        descriptions)]
    if re.search(r"(?:范围|间隔)?不超过\s*[一1]\s*年", descriptions):
        maximums.append(365)
    retentions = [int(value) for value in re.findall(
        r"(?:仅支持|只能查询)?\s*最近\s*(\d+)\s*天", descriptions)]
    return (min(maximums) if maximums else None,
            min(retentions) if retentions else None)


def extract_contract(document: str, *, method: str, path: str) -> ExtractedContract:
    lines = document.replace("\r\n", "\n").splitlines()
    request_lines, _ = _section(lines, ("请求参数", "request parameters"))
    response_lines, has_response = _section(
        lines, ("返回结果", "返回参数", "响应参数", "response", "response parameters"))
    request_fields = _fields(request_lines)
    response_fields = _fields(response_lines)
    interface_matches, capacity = _interface(document, path, method)
    request_names = {field["name"] for field in request_fields}
    required = sorted({field["name"] for field in request_fields if field["required"]})
    scope = sorted(name for name in request_names if _normalized_name(name) in _SCOPE_NAMES)
    window_candidates = [field for field in request_fields if _is_window_field(field["name"])]
    required_window = list(dict.fromkeys(
        field["name"] for field in window_candidates if field["required"]))
    window = (required_window if len(required_window) in {1, 2}
              else list(dict.fromkeys(field["name"] for field in window_candidates)))
    window.sort(key=lambda name: (0 if any(token in _normalized_name(name)
                                           for token in ("start", "begin", "after")) else
                                  2 if any(token in _normalized_name(name)
                                           for token in ("end", "finish", "before")) else 1,
                                  name))
    window_descriptions = " ".join(
        field["description"] for field in request_fields if field["name"] in window)
    window_format = ("datetime" if any(token in window_descriptions.lower()
                                        for token in (
                                            "h:i:s", "h:m:s", "hh:mm:ss", "hh-mm-ss", "时分秒"))
                     or any(_normalized_name(name).endswith("time") for name in window)
                     else "date" if window else "unknown")
    max_window_days, retention_days = _window_limits(request_fields, window)
    rows, total = _response_paths(response_fields)
    if not interface_matches:
        status = "document_changed"
    elif not has_response or not response_fields:
        status = "schema_pending"
    else:
        status = "confirmed"
    return {
        "request_fields": request_fields,
        "response_fields": response_fields,
        "required_fields": required,
        "scope_fields": scope,
        "pagination_mode": _pagination(request_names),
        "window_fields": window,
        "window_format": window_format,
        "rows_path": rows,
        "total_path": total,
        "rate_capacity": capacity,
        "max_window_days": max_window_days,
        "retention_days": retention_days,
        "extraction_status": status,
    }
