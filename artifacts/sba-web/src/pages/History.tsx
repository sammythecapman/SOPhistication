import React, { useState } from "react";
import { Link } from "wouter";
import { format, parseISO } from "date-fns";
import { FileText, ArrowRight, Search, FileSearch } from "lucide-react";
import { useListExtractions } from "@workspace/api-client-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { formatCurrency } from "@/lib/utils";

export default function History() {
  const { data, isLoading } = useListExtractions({ page: 1, per_page: 50 });
  const [query, setQuery] = useState("");

  const extractions = data?.extractions ?? [];
  const filtered = query.trim()
    ? extractions.filter((ext) => {
        const q = query.toLowerCase();
        return (
          (ext.borrower_name ?? "").toLowerCase().includes(q) ||
          (ext.deal_type ?? "").toLowerCase().includes(q) ||
          (ext.terms_filename ?? "").toLowerCase().includes(q) ||
          (ext.credit_memo_filename ?? "").toLowerCase().includes(q)
        );
      })
    : extractions;

  return (
    <div className="w-full max-w-6xl mx-auto space-y-8 pb-20">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-8 animate-in fade-in slide-in-from-top-4 duration-500">
        <div>
          <h1 className="text-4xl font-serif font-bold text-foreground tracking-tight mb-3">
            Extraction History
          </h1>
          <p className="text-muted-foreground text-lg">
            Review and download previously processed SBA loan documents.
          </p>
        </div>
        
        <div className="relative w-full md:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search borrowers..."
            className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-border bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-[#D4523A]/20 text-sm"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <Card key={i} className="h-24 animate-pulse bg-slate-100/50 border-0" />
          ))}
        </div>
      ) : filtered.length > 0 ? (
        <div className="grid gap-4 animate-in fade-in slide-in-from-bottom-4 duration-500 delay-150">
          {filtered.map((ext) => (
            <Link key={ext.id} href={`/extraction/${ext.id}`}>
              <Card className="group cursor-pointer hover:shadow-md transition-all duration-200 border-border hover:border-[#D4523A]/40 bg-white">
                <CardContent className="p-5 flex flex-col md:flex-row items-start md:items-center gap-6">
                  
                  <div className="flex items-center gap-4 min-w-[250px]">
                    <div className="p-3 bg-muted group-hover:bg-[#D4523A]/10 group-hover:text-[#D4523A] transition-colors rounded-xl text-muted-foreground">
                      <FileText className="w-6 h-6" />
                    </div>
                    <div>
                      <h3 className="font-serif font-semibold text-lg text-foreground group-hover:text-[#D4523A] transition-colors line-clamp-1">
                        {ext.borrower_name || "Unknown Borrower"}
                      </h3>
                      <p className="text-xs text-muted-foreground mt-1">
                        {format(parseISO(ext.created_at), "MMM d, yyyy • h:mm a")}
                      </p>
                    </div>
                  </div>

                  <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-4 w-full text-sm">
                    <div>
                      <p className="text-slate-500 text-xs uppercase tracking-wider mb-1">Deal Type</p>
                      <p className="font-medium text-slate-900 truncate">{ext.deal_type || "—"}</p>
                    </div>
                    <div>
                      <p className="text-slate-500 text-xs uppercase tracking-wider mb-1">Amount</p>
                      <p className="font-medium text-slate-900">{formatCurrency(ext.loan_amount)}</p>
                    </div>
                    <div className="md:col-span-2">
                      <p className="text-slate-500 text-xs uppercase tracking-wider mb-1">
                        Source {ext.credit_memo_filename ? "Files" : "File"}
                      </p>
                      <p className="text-slate-700 truncate text-sm" title={ext.terms_filename}>
                        {ext.terms_filename}
                      </p>
                      {ext.credit_memo_filename && (
                        <p className="text-slate-500 truncate text-sm mt-0.5" title={ext.credit_memo_filename}>
                          + {ext.credit_memo_filename}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-6 md:ml-auto w-full md:w-auto mt-4 md:mt-0 pt-4 md:pt-0 border-t md:border-t-0 border-slate-100">
                    <div className="text-right">
                      <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Quality</p>
                      <div className="flex items-center gap-2">
                        {ext.has_ner_warnings && (
                          <div className="w-2 h-2 rounded-full bg-amber-500" title="Has Review Warnings" />
                        )}
                        <p className="font-semibold text-foreground">{Math.round(ext.completion_pct)}%</p>
                      </div>
                    </div>
                    <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center group-hover:bg-[#D4523A] group-hover:text-white transition-colors">
                      <ArrowRight className="w-5 h-5" />
                    </div>
                  </div>
                  
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      ) : query.trim() ? (
        <div className="text-center py-32 bg-white rounded-2xl border border-dashed border-slate-300">
          <Search className="w-16 h-16 mx-auto text-slate-300 mb-4" />
          <h3 className="text-xl font-serif font-medium text-slate-900 mb-2">No results for "{query}"</h3>
          <p className="text-slate-500 max-w-sm mx-auto mb-6">
            Try a different borrower name, deal type, or filename.
          </p>
          <Button variant="outline" onClick={() => setQuery("")}>Clear search</Button>
        </div>
      ) : (
        <div className="text-center py-32 bg-white rounded-2xl border border-dashed border-slate-300">
          <FileSearch className="w-16 h-16 mx-auto text-slate-300 mb-4" />
          <h3 className="text-xl font-serif font-medium text-slate-900 mb-2">No extractions yet</h3>
          <p className="text-slate-500 max-w-sm mx-auto mb-6">
            You haven't processed any SBA loan documents. Head back to the dashboard to start your first extraction.
          </p>
          <Link href="/">
            <Button>Start New Extraction</Button>
          </Link>
        </div>
      )}
    </div>
  );
}
