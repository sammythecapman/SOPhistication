import React from "react";
import { Link, useLocation } from "wouter";
import { FileText, History, Scale, Menu, X } from "lucide-react";
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
        className="md:hidden fixed top-4 right-4 z-50 p-2 bg-white rounded-md shadow-sm border"
        onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
      >
        {isMobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </button>

      {/* Sidebar */}
      <aside className={cn(
        "fixed inset-y-0 left-0 z-40 w-64 bg-primary text-primary-foreground flex flex-col transition-transform duration-300 ease-in-out md:translate-x-0",
        isMobileMenuOpen ? "translate-x-0" : "-translate-x-full"
      )}>
        <div className="p-6 flex items-center gap-3 border-b border-primary-foreground/10">
          <div className="bg-primary-foreground/10 p-2 rounded-lg">
            <Scale className="h-6 w-6 text-primary-foreground" />
          </div>
          <div>
            <h1 className="font-serif text-xl font-bold tracking-wide">LexExtract</h1>
            <p className="text-xs text-primary-foreground/60 tracking-wider uppercase">SBA Document Analysis</p>
          </div>
        </div>

        <nav className="flex-1 px-4 py-6 space-y-2">
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
                    ? "bg-primary-foreground/10 text-white" 
                    : "text-primary-foreground/70 hover:bg-primary-foreground/5 hover:text-white"
                )}
              >
                <Icon className="h-5 w-5" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        
        <div className="p-6 border-t border-primary-foreground/10">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-full bg-primary-foreground/20 flex items-center justify-center font-serif font-bold text-sm">
              LF
            </div>
            <div className="text-sm">
              <p className="font-medium">Law Firm Portal</p>
              <p className="text-xs text-primary-foreground/60">v1.0.0</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 md:ml-64 relative min-h-screen">
        {/* Subtle decorative background overlay */}
        <div 
          className="absolute inset-0 z-0 opacity-[0.03] pointer-events-none bg-repeat"
          style={{ backgroundImage: `url(${import.meta.env.BASE_URL}images/law-bg.png)` }}
        />
        <div className="relative z-10 w-full h-full p-4 md:p-8 lg:p-12 max-w-7xl mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
