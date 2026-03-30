import React from "react";
import { useParams, Link } from "wouter";
import { useGetExtraction } from "@workspace/api-client-react";
import { ResultsView } from "./Results";
import { ArrowLeft, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ExtractionView() {
  const params = useParams();
  const id = parseInt(params.id || "0", 10);

  const { data, isLoading, isError } = useGetExtraction(id);

  if (isLoading) {
    return (
      <div className="w-full h-[60vh] flex flex-col items-center justify-center">
        <Loader2 className="w-8 h-8 text-primary animate-spin mb-4" />
        <p className="text-slate-500 font-medium">Loading extraction details...</p>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="w-full py-20 text-center">
        <h2 className="text-2xl font-serif text-slate-900 mb-2">Extraction Not Found</h2>
        <p className="text-slate-500 mb-6">This extraction record might have been deleted.</p>
        <Link href="/history">
          <Button>Return to History</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="w-full max-w-5xl mx-auto pb-20">
      <div className="mb-6">
        <Link href="/history" className="inline-flex items-center text-sm font-medium text-slate-500 hover:text-primary transition-colors">
          <ArrowLeft className="w-4 h-4 mr-1" />
          Back to History
        </Link>
      </div>
      <ResultsView extraction={data} />
    </div>
  );
}
