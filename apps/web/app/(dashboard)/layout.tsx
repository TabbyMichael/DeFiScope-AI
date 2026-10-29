import Link from "next/link";
import { Suspense } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import { ModeToggle } from "@/components/mode-toggle";
import { Separator } from "@/components/ui/separator";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { API_PUBLIC_URL } from "@/lib/api";

export default function DashboardLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <SidebarProvider>
      <Suspense fallback={<div data-slot="sidebar" className="hidden w-0" aria-hidden />}>
        <AppSidebar />
      </Suspense>
      <SidebarInset>
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-1 h-4" />
          <span className="hidden truncate text-sm text-muted-foreground sm:block">
            DeFi protocol research &amp; risk monitoring
          </span>
          <div className="ml-auto flex items-center gap-1 text-xs sm:gap-3">
            <div className="hidden items-center gap-3 sm:flex">
              <Link href="/about" className="text-muted-foreground hover:text-foreground">
                Methodology
              </Link>
              <a
                href={`${API_PUBLIC_URL}/docs`}
                target="_blank"
                rel="noreferrer"
                className="text-muted-foreground hover:text-foreground"
              >
                API
              </a>
            </div>
            <ModeToggle />
          </div>
        </header>
        <main className="flex-1 px-4 py-6 sm:px-6">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
