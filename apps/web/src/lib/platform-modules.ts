export const PRODUCT_CENTERS = [
  "企业数据中心",
  "企业知识中心",
  "角色分身中心",
  "数字会议中心",
  "智能分析中心",
  "行动与执行中心",
  "平台管理"
] as const;

export type ProductCenter = (typeof PRODUCT_CENTERS)[number];

export interface PlatformModule {
  key: string;
  label: string;
  navigation: ProductCenter;
  owner: string;
  summary: string;
  milestone: string;
  availability: "foundation" | "planned";
}

export interface PlatformModulesResponse {
  schema_version: 1;
  modules: PlatformModule[];
}

export function validatePlatformModules(modules: PlatformModule[]): string[] {
  const failures: string[] = [];
  const keys = new Set<string>();
  const navigation = new Set<ProductCenter>();
  for (const module of modules) {
    if (keys.has(module.key)) failures.push(`重复模块键：${module.key}`);
    keys.add(module.key);
    navigation.add(module.navigation);
  }
  for (const center of PRODUCT_CENTERS) {
    if (!navigation.has(center)) failures.push(`缺少产品导航：${center}`);
  }
  return failures;
}
