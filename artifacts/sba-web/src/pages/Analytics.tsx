import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { BarChart3, AlertTriangle, CheckCircle2, TrendingUp, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

type FieldStat = {
  field_name: string;
  yellow?: { total: number; correct: number; incorrect: number; false_positive_rate: number };
  red?: { total: number; correct: number; incorrect: number; false_positive_rate: number };
  auto_suppression?: string | null;
};

type FeedbackEvent = {
  id: number;
  extraction_id: number;
  field_name: string;
  extracted_value: string;
  confidence_tier: "red" | "yellow";
  reviewer_verdict: "correct" | "incorrect";
  created_at: string;
};

type QuoteVerification = {
  verifiable_quotes: number;
  unverified_quotes: number;
  unverified_quote_rate: number | null;
};

type AnalyticsData = {
  total_extractions: number;
  total_flags: { red: number; yellow: number };
  total_reviewed: { total: number; false_positives: number; true_positives: number };
  quote_verification?: QuoteVerification;
  field_stats: FieldStat[];
  auto_suppressions: Record<string, string>;
  recent_feedback: FeedbackEvent[];
};

async function fetchAnalytics(): Promise<AnalyticsData> {
  const res = await fetch("/api/analytics");
  if (!res.ok) throw new Error("Failed to load analytics");
  return res.json();
}

function StatCard({ label, value, sub, icon: Icon, color }: {
  label: string; value: string | number; sub?: string;
  icon: React.ElementType; color: string;
}) {
  return (
    <Card className="shadow-sm">
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">{label}</p>
            <p className="text-3xl font-semibold text-foreground">{value}</p>
            {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
          </div>
          <div className={cn("p-3 rounded-xl", color)}>
            <Icon className="w-5 h-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function Analytics() {
  const { toast } = useToast();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["analytics"],
    queryFn: fetchAnalytics,
    refetchInterval: 30_000,
  });

  const handleReset = async (fieldName: string) => {
    try {
      await fetch(`/api/analytics/learning/${encodeURIComponent(fieldName)}`, { method: "DELETE" });
      toast({ title: `Learning reset for '${fieldName}'` });
      refetch();
    } catch {
      toast({ title: "Reset failed", variant: "destructive" });
    }
  };

  if (isLoading) {
    return (
      <div className="w-full max-w-6xl mx-auto space-y-4 pb-20">
        <div className="h-8 w-48 bg-slate-100 rounded animate-pulse mb-8" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <Card key={i} className="h-32 animate-pulse bg-slate-100/50 border-0" />)}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="w-full max-w-6xl mx-auto py-20 text-center">
        <p className="text-slate-500">Could not load analytics data.</p>
      </div>
    );
  }

  const totalFlags = data.total_flags.red + data.total_flags.yellow;
  const fpRate = data.total_reviewed.total > 0
    ? Math.round((data.total_reviewed.false_positives / data.total_reviewed.total) * 100)
    : null;

  const qv = data.quote_verification;
  const unverifiedRate = qv && qv.unverified_quote_rate !== null
    ? Math.round(qv.unverified_quote_rate * 100)
    : null;

  return (
    <div className="w-full max-w-6xl mx-auto space-y-8 pb-20">
      <div className="animate-in fade-in slide-in-from-top-4 duration-500">
        <h1 className="text-4xl font-serif font-bold text-foreground tracking-tight mb-3">
          Confidence Analytics
        </h1>
        <p className="text-muted-foreground text-lg">
          Extraction quality metrics and reviewer feedback trends.
        </p>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 animate-in fade-in slide-in-from-bottom-4 duration-500 delay-100">
        <StatCard
          label="Total Extractions"
          value={data.total_extractions}
          icon={BarChart3}
          color="bg-blue-50 text-blue-600"
        />
        <StatCard
          label="Flags Generated"
          value={totalFlags}
          sub={`${data.total_flags.red} high-risk · ${data.total_flags.yellow} advisory`}
          icon={AlertTriangle}
          color="bg-amber-50 text-amber-600"
        />
        <StatCard
          label="Flags Reviewed"
          value={data.total_reviewed.total}
          sub={data.total_reviewed.total > 0
            ? `${data.total_reviewed.false_positives} false positive · ${data.total_reviewed.true_positives} true positive`
            : "No reviews yet"}
          icon={CheckCircle2}
          color="bg-emerald-50 text-emerald-600"
        />
        <StatCard
          label="False Positive Rate"
          value={fpRate !== null ? `${fpRate}%` : "—"}
          sub={fpRate !== null ? "of reviewed flags were false alarms" : "Need reviews to compute"}
          icon={TrendingUp}
          color="bg-[#D4523A]/10 text-[#D4523A]"
        />
      </div>

      {/* Process-supervision: per-field quote verification rate */}
      {qv && qv.verifiable_quotes > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 animate-in fade-in duration-500 delay-150">
          <StatCard
            label="Unverified Quote Rate"
            value={unverifiedRate !== null ? `${unverifiedRate}%` : "—"}
            sub={`${qv.unverified_quotes} of ${qv.verifiable_quotes} model quotes did not appear in source documents`}
            icon={AlertTriangle}
            color={
              unverifiedRate !== null && unverifiedRate >= 10
                ? "bg-red-50 text-red-600"
                : "bg-emerald-50 text-emerald-600"
            }
          />
        </div>
      )}

      {/* Auto-suppressions */}
      {Object.keys(data.auto_suppressions).length > 0 && (
        <Card className="shadow-sm border-emerald-200 bg-emerald-50/40 animate-in fade-in duration-500 delay-150">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2 text-emerald-800">
              <CheckCircle2 className="w-4 h-4" />
              Auto-Suppressed Field Types
            </CardTitle>
            <CardDescription className="text-emerald-700/80">
              These fields have been automatically promoted based on high false-positive rates.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.auto_suppressions).map(([field, rule]) => (
                <div key={field} className="flex items-center gap-2 px-3 py-1.5 bg-white rounded-full border border-emerald-200 text-sm">
                  <span className="font-medium text-slate-800">{field}</span>
                  <span className="text-xs text-emerald-700">
                    {rule === "suppress_yellow" ? "yellow → green" : "red → yellow"}
                  </span>
                  <button
                    onClick={() => handleReset(field)}
                    className="text-slate-400 hover:text-red-500 transition-colors ml-1"
                    title="Reset learning for this field"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Per-field stats table */}
      {data.field_stats.length > 0 && (
        <Card className="shadow-sm animate-in fade-in duration-500 delay-200">
          <CardHeader className="border-b border-border py-4 bg-[hsl(40,20%,97%)]">
            <CardTitle className="text-lg">Per-Field Accuracy</CardTitle>
            <CardDescription>False positive rate per field type from reviewer feedback.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs uppercase tracking-wider text-slate-500">
                    <th className="text-left py-3 px-4">Field</th>
                    <th className="text-center py-3 px-4">Yellow reviews</th>
                    <th className="text-center py-3 px-4">Yellow FP%</th>
                    <th className="text-center py-3 px-4">Red reviews</th>
                    <th className="text-center py-3 px-4">Red FP%</th>
                    <th className="text-center py-3 px-4">Status</th>
                    <th className="text-center py-3 px-4">Reset</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.field_stats.map(stat => {
                    const suppression = stat.auto_suppression;
                    return (
                      <tr key={stat.field_name} className="hover:bg-slate-50/50 transition-colors">
                        <td className="py-3 px-4 font-medium text-slate-900">{stat.field_name}</td>
                        <td className="text-center py-3 px-4 text-slate-600">{stat.yellow?.total ?? "—"}</td>
                        <td className="text-center py-3 px-4">
                          {stat.yellow
                            ? <FPBadge rate={stat.yellow.false_positive_rate} />
                            : <span className="text-slate-400">—</span>}
                        </td>
                        <td className="text-center py-3 px-4 text-slate-600">{stat.red?.total ?? "—"}</td>
                        <td className="text-center py-3 px-4">
                          {stat.red
                            ? <FPBadge rate={stat.red.false_positive_rate} />
                            : <span className="text-slate-400">—</span>}
                        </td>
                        <td className="text-center py-3 px-4">
                          {suppression
                            ? <span className="text-xs text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full font-medium">
                                {suppression === "suppress_yellow" ? "Auto-confirmed" : "Auto-downgraded"}
                              </span>
                            : <span className="text-xs text-slate-400">Normal</span>}
                        </td>
                        <td className="text-center py-3 px-4">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-slate-400 hover:text-red-500 h-7 w-7 p-0"
                            onClick={() => handleReset(stat.field_name)}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recent feedback */}
      {data.recent_feedback.length > 0 && (
        <Card className="shadow-sm animate-in fade-in duration-500 delay-300">
          <CardHeader className="border-b border-border py-4 bg-[hsl(40,20%,97%)]">
            <CardTitle className="text-lg">Recent Feedback</CardTitle>
            <CardDescription>Last {data.recent_feedback.length} reviewer verdicts.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs uppercase tracking-wider text-slate-500">
                    <th className="text-left py-3 px-4">Field</th>
                    <th className="text-left py-3 px-4">Extracted value</th>
                    <th className="text-center py-3 px-4">Tier</th>
                    <th className="text-center py-3 px-4">Verdict</th>
                    <th className="text-left py-3 px-4">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.recent_feedback.map(fb => (
                    <tr key={fb.id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="py-3 px-4 font-medium text-slate-800">{fb.field_name}</td>
                      <td className="py-3 px-4 text-slate-600 max-w-[180px] truncate" title={fb.extracted_value}>
                        {fb.extracted_value}
                      </td>
                      <td className="text-center py-3 px-4">
                        <span className={cn(
                          "text-xs px-2 py-0.5 rounded-full font-medium",
                          fb.confidence_tier === "red"
                            ? "bg-red-100 text-red-700"
                            : "bg-amber-100 text-amber-700"
                        )}>
                          {fb.confidence_tier}
                        </span>
                      </td>
                      <td className="text-center py-3 px-4">
                        <span className={cn(
                          "text-xs px-2 py-0.5 rounded-full font-medium",
                          fb.reviewer_verdict === "correct"
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-red-100 text-red-700"
                        )}>
                          {fb.reviewer_verdict}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-500 text-xs">
                        {new Date(fb.created_at).toLocaleDateString("en-US", {
                          month: "short", day: "numeric", year: "numeric"
                        })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {data.total_reviewed.total === 0 && data.field_stats.length === 0 && (
        <div className="text-center py-24 bg-white rounded-2xl border border-dashed border-slate-300">
          <BarChart3 className="w-16 h-16 mx-auto text-slate-300 mb-4" />
          <h3 className="text-xl font-serif font-medium text-slate-900 mb-2">No feedback yet</h3>
          <p className="text-slate-500 max-w-sm mx-auto">
            Process extractions and use the confidence feedback buttons to start building accuracy data.
          </p>
        </div>
      )}
    </div>
  );
}

function FPBadge({ rate }: { rate: number }) {
  const pct = Math.round(rate * 100);
  const color = pct >= 90
    ? "bg-emerald-100 text-emerald-700"
    : pct >= 70
    ? "bg-amber-100 text-amber-700"
    : "bg-red-100 text-red-700";
  return (
    <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", color)}>
      {pct}%
    </span>
  );
}
