import React, { useState } from "react";
import { type ExtractionDetail } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Download, Share2, FileCheck2, CheckCircle2, ThumbsUp, ThumbsDown } from "lucide-react";
import { cn, formatCurrency } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

type ConfidenceScore = {
  value: string;
  confidence_tier: "green" | "yellow" | "red";
  ner_match: boolean;
  source_text_match: boolean;
  source_snippet: string | null;
  match_details: string;
};

type ExtractionDetailExt = ExtractionDetail & {
  confidence_scores?: Record<string, ConfidenceScore>;
};

function categorizeFields(data: Record<string, string>) {
  const categories = {
    Core: {} as Record<string, string>,
    Parties: {} as Record<string, string>,
    PropertyAndConstruction: {} as Record<string, string>,
    Other: {} as Record<string, string>,
  };

  Object.entries(data).forEach(([key, value]) => {
    const k = key.toLowerCase();
    if (k.includes("amount") || k.includes("rate") || k.includes("date") ||
        k.includes("loan") || k.includes("spread") || k.includes("type")) {
      if (k.includes("property") || k.includes("construction") || k.includes("architect") || k.includes("lease")) {
        categories.PropertyAndConstruction[key] = value;
      } else {
        categories.Core[key] = value;
      }
    } else if (k.includes("borrower") || k.includes("lender") || k.includes("guarantor") ||
               k.includes("seller") || k.includes("landlord")) {
      categories.Parties[key] = value;
    } else if (k.includes("property") || k.includes("construction") || k.includes("architect") ||
               k.includes("contract") || k.includes("realestate")) {
      categories.PropertyAndConstruction[key] = value;
    } else {
      categories.Other[key] = value;
    }
  });

  return categories;
}

function ConfidenceDot({ tier, className }: { tier?: "green" | "yellow" | "red"; className?: string }) {
  if (!tier || tier === "green") {
    return (
      <div className={cn("w-2 h-2 rounded-full bg-[#D4523A] shadow-[0_0_8px_rgba(212,82,58,0.35)] shrink-0", className)} />
    );
  }
  if (tier === "yellow") {
    return (
      <div className={cn("w-2 h-2 rounded-full bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.4)] shrink-0", className)} />
    );
  }
  return (
    <div className={cn("w-2 h-2 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.45)] shrink-0 animate-pulse", className)} />
  );
}

function FeedbackButtons({
  extractionId,
  fieldName,
  score,
  submitted,
  onSubmit,
}: {
  extractionId: number;
  fieldName: string;
  score: ConfidenceScore;
  submitted: "correct" | "incorrect" | null;
  onSubmit: (verdict: "correct" | "incorrect") => void;
}) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);

  if (submitted) {
    return (
      <span className="text-xs text-slate-400 flex items-center gap-1">
        <CheckCircle2 className="w-3 h-3" />
        Feedback recorded
      </span>
    );
  }

  const handleClick = async (verdict: "correct" | "incorrect") => {
    setLoading(true);
    try {
      await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          extraction_id: extractionId,
          field_name: fieldName,
          extracted_value: score.value,
          confidence_tier: score.confidence_tier,
          reviewer_verdict: verdict,
        }),
      });
      onSubmit(verdict);
      toast({ title: "Feedback saved", description: `Marked '${fieldName}' as ${verdict}` });
    } catch {
      toast({ title: "Could not save feedback", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-1.5 mt-1">
      <span className="text-[10px] text-slate-400 uppercase tracking-wider">Correct?</span>
      <button
        disabled={loading}
        onClick={() => handleClick("correct")}
        className="flex items-center gap-1 text-xs px-2 py-0.5 rounded border border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 transition-colors disabled:opacity-50"
      >
        <ThumbsUp className="w-3 h-3" /> Yes
      </button>
      <button
        disabled={loading}
        onClick={() => handleClick("incorrect")}
        className="flex items-center gap-1 text-xs px-2 py-0.5 rounded border border-red-200 text-red-700 bg-red-50 hover:bg-red-100 transition-colors disabled:opacity-50"
      >
        <ThumbsDown className="w-3 h-3" /> No
      </button>
    </div>
  );
}

function FieldCard({
  fieldKey,
  value,
  score,
  index,
  extractionId,
}: {
  fieldKey: string;
  value: string;
  score?: ConfidenceScore;
  index: number;
  extractionId: number;
}) {
  const [feedback, setFeedback] = useState<"correct" | "incorrect" | null>(null);
  const hasValue = value && value.trim() !== "";
  const tier = hasValue && score ? score.confidence_tier : undefined;
  const isRed = tier === "red";
  const isYellow = tier === "yellow";
  const showFeedback = (isRed || isYellow) && hasValue;

  return (
    <div
      className={cn(
        "p-4 transition-colors flex items-start gap-3",
        index >= 3 ? "md:border-t border-border" : "",
        isRed ? "bg-red-50/60 hover:bg-red-50" : isYellow ? "bg-amber-50/40 hover:bg-amber-50/60" : "hover:bg-[hsl(40,20%,98%)]"
      )}
    >
      <ConfidenceDot tier={hasValue ? tier : undefined} className="mt-1.5" />
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-muted-foreground mb-1 truncate" title={fieldKey}>
          {fieldKey}
        </p>
        <p className={cn(
          "text-sm break-words",
          hasValue ? "text-foreground font-medium" : "text-muted-foreground italic"
        )}>
          {hasValue ? value : "Not found in document"}
        </p>

        {/* RED — strong hallucination warning */}
        {isRed && hasValue && (
          <div className="mt-2 p-2.5 rounded-md bg-red-100 border border-red-200 text-xs text-red-800 leading-relaxed">
            <span className="font-bold">⛔ Not found in source text.</span>{" "}
            This value was not located anywhere in the uploaded document. Verify manually before use.
          </div>
        )}

        {/* YELLOW — NER gap advisory with snippet */}
        {isYellow && hasValue && (
          <div className="mt-2 p-2.5 rounded-md bg-amber-50 border border-amber-200 text-xs text-amber-800 leading-relaxed">
            <span className="font-medium">⚠ NER coverage gap.</span>{" "}
            Value found in source text but not tagged as a named entity — low hallucination risk.
            {score?.source_snippet && (
              <div className="mt-1.5 font-mono text-[10px] text-amber-700 bg-amber-100/80 rounded px-2 py-1 break-words">
                "{score.source_snippet}"
              </div>
            )}
          </div>
        )}

        {showFeedback && (
          <FeedbackButtons
            extractionId={extractionId}
            fieldName={fieldKey}
            score={score!}
            submitted={feedback}
            onSubmit={setFeedback}
          />
        )}
      </div>
    </div>
  );
}

export function ResultsView({ extraction }: { extraction: ExtractionDetailExt }) {
  const categories = categorizeFields(extraction.formatted_data);
  const scores = extraction.confidence_scores ?? {};
  const totalPopulated = extraction.fields_populated;
  const totalFields = extraction.fields_total;
  const completion = Math.round((totalPopulated / (totalFields || 1)) * 100);

  const redCount = Object.values(scores).filter(s => s.confidence_tier === "red").length;
  const yellowCount = Object.values(scores).filter(s => s.confidence_tier === "yellow").length;

  const handleDownload = () => {
    window.location.href = `/api/extractions/${extraction.id}/download`;
  };

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">

      {/* Header Summary Card */}
      <Card className="bg-gradient-to-br from-white to-[hsl(40,20%,97%)] border-border shadow-sm overflow-hidden relative">
        <div className="absolute top-0 right-0 p-8 opacity-5">
          <FileCheck2 className="w-32 h-32" />
        </div>
        <CardContent className="p-8">
          <div className="flex flex-col md:flex-row justify-between gap-6">
            <div className="space-y-4 relative z-10">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <span className="px-3 py-1 bg-[#D4523A]/10 text-[#D4523A] text-xs font-semibold rounded-full uppercase tracking-wider">
                    {extraction.deal_structure?.deal_type || "SBA Loan"}
                  </span>
                  <span className="text-sm text-muted-foreground font-medium">ID: #{extraction.id}</span>
                </div>
                <h2 className="text-3xl font-serif font-bold text-foreground">
                  {extraction.formatted_data["Borrower1Name"] || "Unknown Borrower"}
                </h2>
                <p className="text-muted-foreground mt-1 flex items-center gap-2">
                  <FileTextIcon className="w-4 h-4" />
                  Source: <span className="font-medium text-foreground">{extraction.terms_filename}</span>
                </p>
              </div>

              <div className="flex items-center gap-6 pt-2 flex-wrap">
                <div>
                  <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Loan Amount</p>
                  <p className="text-xl font-semibold text-foreground">
                    {formatCurrency(extraction.formatted_data["LoanAmountShort"])}
                  </p>
                </div>
                <div className="w-px h-10 bg-border" />
                <div>
                  <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Data Completion</p>
                  <div className="flex items-center gap-2">
                    <p className="text-xl font-semibold text-foreground">{completion}%</p>
                    <span className="text-xs text-muted-foreground">({totalPopulated}/{totalFields} fields)</span>
                  </div>
                </div>
                {(redCount > 0 || yellowCount > 0) && (
                  <>
                    <div className="w-px h-10 bg-border" />
                    <div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Confidence Flags</p>
                      <div className="flex items-center gap-2">
                        {redCount > 0 && (
                          <span className="flex items-center gap-1 text-xs font-semibold text-red-700 bg-red-100 px-2 py-0.5 rounded-full">
                            <span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block" />
                            {redCount} high-risk
                          </span>
                        )}
                        {yellowCount > 0 && (
                          <span className="flex items-center gap-1 text-xs font-semibold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
                            {yellowCount} advisory
                          </span>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="flex flex-col gap-3 justify-center min-w-[200px] z-10">
              <Button onClick={handleDownload} className="w-full justify-start gap-2 h-12 shadow-sm bg-[#D4523A] hover:bg-[#B83F28] text-white">
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

      {/* Legend */}
      {Object.keys(scores).length > 0 && (
        <div className="flex items-center gap-6 px-1 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-[#D4523A] inline-block" /> Confirmed
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" /> NER gap (low risk)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-red-500 inline-block" /> Not found in source
          </span>
        </div>
      )}

      {/* Field Grid */}
      <div className="space-y-6">
        {Object.entries(categories).map(([categoryName, fields]) => {
          if (Object.keys(fields).length === 0) return null;

          return (
            <Card key={categoryName} className="shadow-sm">
              <CardHeader className="bg-[hsl(40,20%,97%)] border-b border-border py-4">
                <CardTitle className="text-lg font-sans flex items-center gap-2 text-foreground">
                  {categoryName.replace(/([A-Z])/g, " $1").trim()}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-slate-100">
                  {Object.entries(fields).map(([key, value], index) => (
                    <FieldCard
                      key={key}
                      fieldKey={key}
                      value={value}
                      score={scores[key]}
                      index={index}
                      extractionId={extraction.id}
                    />
                  ))}
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
    <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24"
      viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
      <path d="M14 2v4a2 2 0 0 0 2 2h4" />
      <path d="M10 9H8" />
      <path d="M16 13H8" />
      <path d="M16 17H8" />
    </svg>
  );
}
