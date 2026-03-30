import React from "react";
import { Link, useLocation } from "wouter";
import { FileText, History, Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false);

  const navItems = [
    { href: "/", label: "New Extraction", icon: FileText },
    { href: "/history", label: "Extraction History", icon: History },
  ];

  return (
    <div className="min-h-screen bg-background flex w-full font-sans">
      {/* Mobile Menu Button */}
      <button
        className="md:hidden fixed top-4 right-4 z-50 p-2 bg-white rounded-md shadow-sm border border-border"
        onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
      >
        {isMobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </button>

      {/* Sidebar */}
      <aside className={cn(
        "fixed inset-y-0 left-0 z-40 w-64 bg-primary text-primary-foreground flex flex-col transition-transform duration-300 ease-in-out md:translate-x-0",
        isMobileMenuOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        {/* Logo / Brand */}
        <div className="p-6 flex items-center gap-3 border-b border-primary-foreground/10">
          {/* JB monogram mark — styled after the firm's rounded square logo */}
          <div className="w-10 h-10 rounded-lg bg-[#D4523A] flex items-center justify-center shrink-0 shadow-md">
            <span className="font-bold text-white text-sm tracking-wider">JB</span>
          </div>
          <div>
            <h1 className="font-serif text-base font-bold tracking-widest uppercase leading-tight">
              Johnson Bealka
            </h1>
            <p className="text-[10px] text-primary-foreground/55 tracking-widest uppercase mt-0.5">
              SBA Loan Portal
            </p>
          </div>
        </div>

        <nav className="flex-1 px-4 py-6 space-y-1">
          {navItems.map((item) => {
            const isActive = location === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setIsMobileMenuOpen(false)}
                className={cn(
                  "flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors",
                  isActive
                    ? "bg-[#D4523A]/20 text-[#D4523A] border-l-2 border-[#D4523A]"
                    : "text-primary-foreground/65 hover:bg-primary-foreground/5 hover:text-primary-foreground"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="p-6 border-t border-primary-foreground/10">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-full bg-[#D4523A]/30 flex items-center justify-center font-bold text-xs text-[#D4523A]">
              JB
            </div>
            <div className="text-sm">
              <p className="font-semibold text-primary-foreground/90 tracking-wide text-xs uppercase">Johnson Bealka, PLLC</p>
              <p className="text-[10px] text-primary-foreground/45 mt-0.5">v1.0.0</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 md:ml-64 relative min-h-screen">
        <div className="relative z-10 w-full h-full p-4 md:p-8 lg:p-12 max-w-7xl mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
