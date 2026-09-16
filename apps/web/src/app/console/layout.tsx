import { Suspense } from "react";

import { ConsoleExperience } from "@/components/console/console-shell";

export default function ConsoleLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <Suspense fallback={<div className="app-loading">正在加载管理台…</div>}>
      <ConsoleExperience>{children}</ConsoleExperience>
    </Suspense>
  );
}

