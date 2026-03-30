import React from "react";
import { type ExtractionDetail } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Download, Share2, AlertTriangle, FileCheck2, Info } from "lucide-react";
import { cn, formatCurrency } from "@/lib/utils";

// Helper to categorize fields for better legal review UX
function categorizeFields(data: Record<string, string>) {
  const categories = {
    Core: {} as Record<string, string>,
    Parties: {} as Record<string, string>,
    PropertyAndConstruction: {} as Record<string, string>,
    Other: {} as Record<string, string>,
  };

  Object.entries(data).forEach(([key, value]) => {
    const k = key.toLowerCase();
    if (
      k.includes("amount") || k.includes("rate") || k.includes("date") || 
      k.includes("loan") || k.includes("spread") || k.includes("type")
    ) {
      if (k.includes("property") || k.includes("construction") || k.includes("architect") || k.includes("lease")) {
        categories.PropertyAndConstruction[key] = value;
      } else {
        categories.Core[key] = value;
      }
    } else if (
      k.includes("borrower") || k.includes("lender") || k.includes("guarantor") || 
      k.includes("seller") || k.includes("landlord")
    ) {
      categories.Parties[key] = value;
    } else if (
      k.includes("property") || k.includes("construction") || k.includes("architect") || 
      k.includes("contract") || k.includes("realestate")
    ) {
      categories.PropertyAndConstruction[key] = value;
    } else {
      categories.Other[key] = value;
    }
  });

  return categories;
}

export function ResultsView({ extraction }: { extraction: ExtractionDetail }) {
  const categories = categorizeFields(extraction.formatted_data);
  const totalPopulated = extraction.fields_populated;
  const totalFields = extraction.fields_total;
  const completion = Math.round((totalPopulated / (totalFields || 1)) * 100);

  const handleDownload = () => {
    window.location.href = `/api/extractions/${extraction.id}/download`;
  };

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      
      {/* Header Summary Card */}
      <Card className="bg-gradient-to-br from-white to-slate-50 border-slate-200 shadow-sm overflow-hidden relative">
        <div className="absolute top-0 right-0 p-8 opacity-5">
          <FileCheck2 className="w-32 h-32" />
        </div>
        <CardContent className="p-8">
          <div className="flex flex-col md:flex-row justify-between gap-6">
            <div className="space-y-4 relative z-10">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <span className="px-3 py-1 bg-primary/10 text-primary text-xs font-semibold rounded-full uppercase tracking-wider">
                    {extraction.deal_structure?.deal_type || "SBA Loan"}
                  </span>
                  <span className="text-sm text-muted-foreground font-medium">
                    ID: #{extraction.id}
                  </span>
                </div>
                <h2 className="text-3xl font-serif font-bold text-slate-900">
                  {extraction.formatted_data["Borrower1Name"] || "Unknown Borrower"}
                </h2>
                <p className="text-slate-500 mt-1 flex items-center gap-2">
                  <FileTextIcon className="w-4 h-4" /> 
                  Source: <span className="font-medium text-slate-700">{extraction.terms_filename}</span>
                </p>
              </div>
              
              <div className="flex items-center gap-6 pt-2">
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Loan Amount</p>
                  <p className="text-xl font-semibold text-slate-900">
                    {formatCurrency(extraction.formatted_data["LoanAmountShort"])}
                  </p>
                </div>
                <div className="w-px h-10 bg-slate-200" />
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Data Completion</p>
                  <div className="flex items-center gap-2">
                    <p className="text-xl font-semibold text-slate-900">{completion}%</p>
                    <span className="text-xs text-slate-500">({totalPopulated}/{totalFields} fields)</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-3 justify-center min-w-[200px] z-10">
              <Button onClick={handleDownload} className="w-full justify-start gap-2 h-12 shadow-sm">
                <Download className="w-4 h-4" />
                Download JSON Data
              </Button>
              
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span tabIndex={0}>
                      <Button variant="outline" className="w-full justify-start gap-2 h-12 bg-white" disabled>
                        <Share2 className="w-4 h-4 text-slate-400" />
                        <span className="text-slate-500">Push to SharePoint</span>
                      </Button>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" className="bg-slate-900 text-white border-none shadow-lg">
                    <p>SharePoint integration coming soon.</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Warnings */}
      {extraction.ner_warnings && extraction.ner_warnings.length > 0 && (
        <Card className="border-amber-200 bg-amber-50 shadow-sm">
          <CardHeader className="pb-3 border-b border-amber-100/50">
            <CardTitle className="text-lg font-sans text-amber-900 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
              Extraction Warnings
            </CardTitle>
            <CardDescription className="text-amber-700/80">
              The NLP engine flagged the following items for human review.
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            <ul className="space-y-2">
              {extraction.ner_warnings.map((warning, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-amber-800">
                  <div className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-1.5 shrink-0" />
                  <span>{warning}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Field Grid */}
      <div className="space-y-6">
        {Object.entries(categories).map(([categoryName, fields]) => {
          if (Object.keys(fields).length === 0) return null;
          
          return (
            <Card key={categoryName} className="shadow-sm">
              <CardHeader className="bg-slate-50/50 border-b border-slate-100 py-4">
                <CardTitle className="text-lg font-sans flex items-center gap-2 text-slate-800">
                  {categoryName.replace(/([A-Z])/g, ' $1').trim()}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-slate-100">
                  {/* We flatten the grid by row, adding bottom borders */}
                  {Object.entries(fields).map(([key, value], index) => {
                    const hasValue = value && value.trim() !== "";
                    return (
                      <div 
                        key={key} 
                        className={cn(
                          "p-4 hover:bg-slate-50/50 transition-colors flex items-start gap-3",
                          index >= 3 ? "md:border-t border-slate-100" : ""
                        )}
                      >
                        <div className={cn(
                          "w-2 h-2 rounded-full mt-1.5 shrink-0",
                          hasValue ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]" : "bg-slate-200"
                        )} />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium text-slate-500 mb-1 truncate" title={key}>
                            {key}
                          </p>
                          <p className={cn(
                            "text-sm break-words",
                            hasValue ? "text-slate-900 font-medium" : "text-slate-400 italic"
                          )}>
                            {hasValue ? value : "Not found in document"}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

    </div>
  );
}

function FileTextIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
      <path d="M14 2v4a2 2 0 0 0 2 2h4" />
      <path d="M10 9H8" />
      <path d="M16 13H8" />
      <path d="M16 17H8" />
    </svg>
  )
}
