import React, { useState } from "react";
import { type ExtractionDetail } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Download, Share2, FileCheck2, CheckCircle2, ThumbsUp, ThumbsDown, ChevronDown, FileText, AlertTriangle, X } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn, formatCurrency } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

type ConfidenceScore = {
  value: string;
  confidence_tier: "green" | "yellow" | "red";
  ner_match: boolean;
  source_text_match: boolean;
  source_snippet: string | null;
  match_details: string;
  // Process-supervision additions (v2 prompt). Older rows omit these fields.
  model_cited_source?: string;
  cited_source_in_document?: boolean | null;
};

type StageFailure = {
  stage: string;
  reason: string;
  message: string;
  raw_excerpt?: string;
};

type ExtractionHealth = {
  degraded: boolean;
  stage_failures: StageFailure[];
};

// Per-field source citation produced by the v2 field_extraction prompt.
// `quote` is the verbatim model citation, the literal "[regex_fallback]"
// sentinel for fields filled by regex, or "" when the model returned no
// quote. `verified` is True/False/null per the backend contract.
type FieldSource = {
  quote: string;
  verified: boolean | null;
};

type ExtractionDetailExt = ExtractionDetail & {
  confidence_scores?: Record<string, ConfidenceScore>;
  field_sources?: Record<string, FieldSource>;
  extraction_health?: ExtractionHealth;
};

const SOURCE_QUOTE_MAX_CHARS = 150;

function truncateQuote(q: string): string {
  if (q.length <= SOURCE_QUOTE_MAX_CHARS) return q;
  return q.slice(0, SOURCE_QUOTE_MAX_CHARS - 1).trimEnd() + "…";
}

function FieldSourceCitation({ source }: { source: FieldSource }) {
  // Pipeline-internal provenance sentinels: render a tiny gray pill rather
  // than the literal sentinel text, and never show "Unverified quote" for
  // these (they have no quote to verify).
  if (source.quote === "[regex_fallback]") {
    return (
      <div className="mt-2 inline-flex items-center gap-1 text-[10px] uppercase tracking-wider font-medium text-slate-500 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-full">
        Pattern-matched
      </div>
    );
  }
  if (source.quote === "[deal_analysis]") {
    return (
      <div className="mt-2 inline-flex items-center gap-1 text-[10px] uppercase tracking-wider font-medium text-slate-500 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-full">
        From deal classification
      </div>
    );
  }
  if (!source.quote) return null;

  const quote = truncateQuote(source.quote);
  const isUnverified = source.verified === false;

  return (
    <div className="mt-2 border-l-2 border-[#D4523A] pl-2.5">
      {isUnverified && (
        <div className="flex items-center gap-1 mb-1 text-[10px] font-semibold uppercase tracking-wider text-red-700">
          <AlertTriangle className="w-3 h-3" />
          Unverified quote
        </div>
      )}
      <p className="text-xs text-muted-foreground italic font-mono break-words leading-snug">
        <span className="not-italic font-sans font-medium text-slate-500 mr-1">
          Source:
        </span>
        “{quote}”
      </p>
    </div>
  );
}

const STAGE_LABELS: Record<string, string> = {
  deal_analysis: "Deal structure analysis",
  field_extraction: "Field extraction",
};

const REASON_HINTS: Record<string, string> = {
  json_decode: "the AI returned a malformed response, so the schema may be incomplete",
  api_error: "the AI service was unreachable or returned an error",
};

function formatStageFailure(f: StageFailure): string {
  const stage = STAGE_LABELS[f.stage] || f.stage;
  const hint = REASON_HINTS[f.reason] || "an unexpected error occurred";
  return `${stage} failed — ${hint}. Some fields may be missing or unreliable.`;
}

function HealthBanner({ health }: { health: ExtractionHealth }) {
  const [dismissed, setDismissed] = useState(false);
  if (!health?.degraded || dismissed) return null;

  return (
    <Alert
      role="status"
      className="border-amber-300 bg-amber-50 text-amber-900 [&>svg]:text-amber-600 relative"
    >
      <AlertTriangle className="h-5 w-5" />
      <button
        type="button"
        aria-label="Dismiss warning"
        className="absolute right-3 top-3 text-amber-700 hover:text-amber-900 transition-colors"
        onClick={() => setDismissed(true)}
      >
        <X className="h-4 w-4" />
      </button>
      <AlertTitle className="font-semibold pr-8">
        Partial extraction — review carefully
      </AlertTitle>
      <AlertDescription className="text-amber-800">
        <ul className="list-disc pl-5 space-y-1 mt-1">
          {health.stage_failures.map((f, i) => (
            <li key={i}>{formatStageFailure(f)}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

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

function SourceFilesDropdown({
  extractionId,
  termsFilename,
  creditMemoFilename,
}: {
  extractionId: number;
  termsFilename: string;
  creditMemoFilename: string | null;
}) {
  const { toast } = useToast();
  const [downloading, setDownloading] = React.useState<string | null>(null);

  const files = [
    { label: "Terms & Conditions", name: termsFilename },
    ...(creditMemoFilename ? [{ label: "Credit Memo", name: creditMemoFilename }] : []),
  ];

  const handleSecureDownload = async (filename: string) => {
    if (downloading) return;
    setDownloading(filename);
    try {
      const res = await fetch(
        `/api/extractions/${extractionId}/files/${encodeURIComponent(filename)}/token`
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || "File not available");
      }
      const { token } = await res.json();
      const url = `/api/extractions/${extractionId}/files/${encodeURIComponent(filename)}?token=${token}`;
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Could not download file";
      toast({
        title: "Download unavailable",
        description: message,
        variant: "destructive",
      });
    } finally {
      setDownloading(null);
    }
  };

  if (files.length === 1) {
    return (
      <button
        onClick={() => handleSecureDownload(termsFilename)}
        disabled={downloading === termsFilename}
        className="text-muted-foreground mt-1 flex items-center gap-2 text-sm hover:text-[#D4523A] transition-colors group disabled:opacity-50"
        title="Download source PDF"
      >
        <FileText className="w-4 h-4 shrink-0" />
        <span>Source:</span>
        <span className="font-medium text-foreground group-hover:underline underline-offset-2">
          {downloading === termsFilename ? "Downloading…" : termsFilename}
        </span>
      </button>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="text-muted-foreground mt-1 flex items-center gap-2 text-sm hover:text-foreground transition-colors group">
          <FileText className="w-4 h-4 shrink-0" />
          <span>Sources:</span>
          <span className="font-medium text-foreground underline underline-offset-2 decoration-dashed decoration-slate-400">
            {files.length} documents
          </span>
          <ChevronDown className="w-3.5 h-3.5 text-slate-400 group-hover:text-foreground transition-transform group-data-[state=open]:rotate-180" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[280px] p-1 bg-white shadow-lg">
        {files.map((f, i) => (
          <button
            key={f.name}
            onClick={() => handleSecureDownload(f.name)}
            disabled={downloading === f.name}
            className={cn(
              "w-full flex items-start gap-3 px-3 py-2.5 rounded-md text-left transition-colors",
              "hover:bg-slate-50 active:bg-slate-100 disabled:opacity-50",
              i < files.length - 1 ? "border-b border-slate-100" : ""
            )}
          >
            <FileText className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-0.5">{f.label}</p>
              <p className="text-sm font-medium text-slate-900 leading-snug">{f.name}</p>
              <p className="text-[10px] text-slate-400 mt-0.5">
                {downloading === f.name ? "Downloading…" : "Click to download"}
              </p>
            </div>
          </button>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ConfidenceDot({ tier, hasValue, className }: {
  tier?: "green" | "yellow" | "red";
  hasValue: boolean;
  className?: string;
}) {
  if (!hasValue) {
    return <div className={cn("w-2 h-2 rounded-full bg-muted-foreground/20 shrink-0", className)} />;
  }
  if (tier === "green") {
    return <div className={cn("w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)] shrink-0", className)} />;
  }
  if (tier === "yellow") {
    return <div className={cn("w-2 h-2 rounded-full bg-yellow-400 shadow-[0_0_8px_rgba(234,179,8,0.5)] shrink-0", className)} />;
  }
  if (tier === "red") {
    return <div className={cn("w-2 h-2 rounded-full bg-red-600 shadow-[0_0_8px_rgba(220,38,38,0.6)] shrink-0 animate-pulse", className)} />;
  }
  // Field has a value but isn't scored by the confidence engine (amounts, dates, etc.) — treat as confirmed
  return <div className={cn("w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)] shrink-0", className)} />;
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
  source,
  index,
  extractionId,
}: {
  fieldKey: string;
  value: string;
  score?: ConfidenceScore;
  source?: FieldSource;
  index: number;
  extractionId: number;
}) {
  const [feedback, setFeedback] = useState<"correct" | "incorrect" | null>(null);
  const hasValue = !!(value && value.trim() !== "");
  const tier = score?.confidence_tier;
  const isRed = tier === "red" && hasValue;
  const isYellow = tier === "yellow" && hasValue;
  const showFeedback = (isRed || isYellow);

  return (
    <div
      className={cn(
        "p-4 transition-colors flex items-start gap-3 border-b border-r border-slate-100",
        isRed ? "bg-red-50/60 hover:bg-red-50" : isYellow ? "bg-yellow-50/40 hover:bg-yellow-50/60" : "hover:bg-[hsl(40,20%,98%)]"
      )}
    >
      <ConfidenceDot tier={tier} hasValue={hasValue} className="mt-1.5" />
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

        {/* Per-field source citation (v2 process supervision). Renders a
            small italic monospace quote with primary-color border-left,
            a red "Unverified quote" badge if Claude fabricated the quote,
            or a gray "Pattern-matched" pill for regex-filled fields.
            Legacy rows without sources render nothing. */}
        {hasValue && source && (
          <FieldSourceCitation source={source} />
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
  const fieldSources = extraction.field_sources ?? {};
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

      {/* Health banner — only shows when degraded */}
      {extraction.extraction_health?.degraded && (
        <HealthBanner health={extraction.extraction_health} />
      )}

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
                <SourceFilesDropdown
                  extractionId={extraction.id}
                  termsFilename={extraction.terms_filename}
                  creditMemoFilename={extraction.credit_memo_filename ?? null}
                />
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
                            <span className="w-1.5 h-1.5 rounded-full bg-red-600 inline-block" />
                            {redCount} high-risk
                          </span>
                        )}
                        {yellowCount > 0 && (
                          <span className="flex items-center gap-1 text-xs font-semibold text-yellow-700 bg-yellow-100 px-2 py-0.5 rounded-full">
                            <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 inline-block" />
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
            <span className="w-2 h-2 rounded-full bg-green-500 inline-block" /> Confirmed
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-yellow-400 inline-block" /> NER gap (low risk)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-red-600 inline-block" /> Not found in source
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
              <CardContent className="p-0 overflow-hidden">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                  {Object.entries(fields).map(([key, value], index) => (
                    <FieldCard
                      key={key}
                      fieldKey={key}
                      value={value}
                      score={scores[key]}
                      source={fieldSources[key]}
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

