"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Bell, BookText, GitCompare, LayoutDashboard, MessageSquareText } from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";

const NAV = [
  { title: "Overview", href: "/", icon: LayoutDashboard },
  { title: "Ask the analyst", href: "/ask", icon: MessageSquareText },
  { title: "Alerts", href: "/alerts", icon: Bell },
  { title: "Compare", href: "/compare", icon: GitCompare },
  { title: "Methodology", href: "/about", icon: BookText },
];

export function AppSidebar({ footer }: { footer?: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link href="/">
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                  <Activity />
                </div>
                <div className="grid flex-1 text-left leading-tight">
                  <span className="truncate font-semibold">DeFiScope AI</span>
                  <span className="truncate text-xs text-muted-foreground">
                    research · risk · monitoring
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Platform</SidebarGroupLabel>
          <SidebarMenu>
            {NAV.map((item) => {
              const Icon = item.icon;
              const active =
                item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href);
              return (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton asChild isActive={active} tooltip={item.title}>
                    <Link href={item.href}>
                      <Icon />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        {footer ?? (
          <div className="px-2 py-1 text-xs leading-relaxed text-muted-foreground group-data-[collapsible=icon]:hidden">
            Data source: DefiLlama public API. Scores measure what TVL data can
            show.
          </div>
        )}
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
