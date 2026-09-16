import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "知行数枢｜企业经营工作台",
  description: "企业数据、知识、角色分身、决策和行动的一体化经营工作台。"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html data-scroll-behavior="smooth" lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
