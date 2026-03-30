import React, { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, UploadCloud, X, ArrowRight, FileCheck, Loader2, CheckCircle2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import { useStartExtraction, useGetJobStatus } from "@workspace/api-client-react";
import { ResultsView } from "./Results";

function FileUploadZone({ 
  title, 
  description, 
  file, 
  onDrop, 
  onRemove, 
  required = false 
}: { 
  title: string; 
  description: string; 
  file: File | null; 
  onDrop: (files: File[]) => void; 
  onRemove: () => void;
  required?: boolean;
}) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1
  });

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-semibold text-foreground">
          {title} {required && <span className="text-destructive">*</span>}
        </label>
      </div>
      
      {!file ? (
        <div 
          {...getRootProps()} 
          className={`
            border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200
            flex flex-col items-center justify-center min-h-[160px]
            ${isDragActive ? 'border-[#D4523A] bg-[#D4523A]/5 scale-[1.02]' : 'border-border hover:border-[#D4523A]/40 hover:bg-background'}
          `}
        >
          <input {...getInputProps()} />
          <div className={`p-3 rounded-full mb-3 ${isDragActive ? 'bg-[#D4523A] text-white' : 'bg-muted text-muted-foreground'}`}>
            <UploadCloud className="w-6 h-6" />
          </div>
          <p className="text-sm font-medium text-foreground mb-1">
            {isDragActive ? "Drop PDF here" : "Drag & drop PDF here"}
          </p>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
      ) : (
        <div className="border border-border rounded-xl p-4 flex items-center justify-between bg-white shadow-sm h-[160px]">
          <div className="flex items-center gap-4 overflow-hidden">
            <div className="p-3 bg-emerald-50 text-emerald-600 rounded-lg shrink-0">
              <FileCheck className="w-8 h-8" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground truncate" title={file.name}>
                {file.name}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {(file.size / 1024 / 1024).toFixed(2)} MB
              </p>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={(e) => { e.stopPropagation(); onRemove(); }} className="text-slate-400 hover:text-destructive shrink-0">
            <X className="w-5 h-5" />
          </Button>
        </div>
      )}
    </div>
  );
}

export default function Home() {
  const { toast } = useToast();
  const [termsFile, setTermsFile] = useState<File | null>(null);
  const [memoFile, setMemoFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const startMutation = useStartExtraction({
    mutation: {
      onSuccess: (data) => {
        setJobId(data.job_id);
      },
      onError: (error) => {
        toast({
          title: "Extraction Failed",
          description: error.error || "Failed to start extraction. Please check your files.",
          variant: "destructive"
        });
      }
    }
  });

  // Poll for job status. TanStack v5 refetchInterval function signature.
  const { data: jobStatus, isError } = useGetJobStatus(jobId || "", {
    query: {
      enabled: !!jobId,
      refetchInterval: (query) => {
        const state = query.state.data?.status;
        if (state === 'pending' || state === 'running') return 1500;
        return false;
      }
    }
  });

  const handleStart = () => {
    if (!termsFile) return;
    startMutation.mutate({ data: { terms_pdf: termsFile, credit_memo_pdf: memoFile || undefined } });
  };

  const handleReset = () => {
    setTermsFile(null);
    setMemoFile(null);
    setJobId(null);
  };

  const isExtracting = !!jobId && (jobStatus?.status === 'pending' || jobStatus?.status === 'running');
  const isComplete = jobStatus?.status === 'complete' && jobStatus.result;
  const isFailed = jobStatus?.status === 'failed' || isError;

  return (
    <div className="w-full max-w-5xl mx-auto space-y-8 pb-20">
      
      {!jobId && (
        <div className="mb-10 animate-in fade-in slide-in-from-top-4 duration-500">
          <h1 className="text-4xl font-serif font-bold text-foreground tracking-tight mb-3">
            New Document Extraction
          </h1>
          <p className="font-sans text-muted-foreground text-lg max-w-2xl">
            Upload SBA Loan Terms & Conditions, Credit Memos, and any supplementary documentation and our legal AI will extract all the critical deal parameters in seconds.
          </p>
        </div>
      )}

      <AnimatePresence mode="wait">
        {!jobId ? (
          <motion.div 
            key="upload"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.3 }}
          >
            <Card className="border border-border shadow-lg bg-white/80 backdrop-blur-xl">
              <CardContent className="p-8 md:p-10">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8 md:gap-12">
                  <FileUploadZone 
                    title="Terms & Conditions PDF"
                    description="The main SBA loan document (Required)"
                    file={termsFile}
                    onDrop={(f) => setTermsFile(f[0])}
                    onRemove={() => setTermsFile(null)}
                    required
                  />
                  <FileUploadZone 
                    title="Credit Memo PDF"
                    description="Supporting documents for better accuracy (Optional)"
                    file={memoFile}
                    onDrop={(f) => setMemoFile(f[0])}
                    onRemove={() => setMemoFile(null)}
                  />
                </div>

                <div className="mt-12 flex justify-end items-center pt-8 border-t border-border">
                  <Button 
                    size="lg" 
                    className="w-full md:w-auto h-14 px-8 text-lg group bg-[#D4523A] hover:bg-[#B83F28] text-white"
                    disabled={!termsFile || startMutation.isPending}
                    isLoading={startMutation.isPending}
                    onClick={handleStart}
                  >
                    Run Extraction
                    <ArrowRight className="ml-2 w-5 h-5 group-hover:translate-x-1 transition-transform" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ) : isExtracting ? (
          <motion.div 
            key="progress"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.4 }}
            className="flex flex-col items-center justify-center py-20"
          >
            <div className="relative w-24 h-24 mb-8">
              <div className="absolute inset-0 border-4 border-muted rounded-full"></div>
              <div className="absolute inset-0 border-4 border-[#D4523A] border-t-transparent rounded-full animate-spin"></div>
              <div className="absolute inset-0 flex items-center justify-center">
                <FileText className="w-8 h-8 text-[#D4523A] animate-pulse" />
              </div>
            </div>
            
            <h2 className="text-2xl font-serif font-bold text-foreground mb-2">Analyzing Documents</h2>
            <p className="text-muted-foreground mb-8 font-medium animate-pulse">
              {jobStatus?.stage_label || "Initializing AI engine..."}
            </p>

            <div className="w-full max-w-md bg-white p-6 rounded-2xl shadow-sm border border-border">
              <div className="flex justify-between text-sm mb-3 font-medium text-foreground">
                <span>Overall Progress</span>
                <span>{jobStatus?.progress || 0}%</span>
              </div>
              <Progress value={jobStatus?.progress || 0} className="h-3" />
            </div>
          </motion.div>
        ) : isComplete ? (
          <motion.div 
            key="results"
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          >
            <div className="flex items-center justify-between mb-8">
              <div className="flex items-center gap-3">
                <div className="bg-[#D4523A]/10 p-2 rounded-full">
                  <CheckCircle2 className="w-6 h-6 text-[#D4523A]" />
                </div>
                <h1 className="text-3xl font-serif font-bold text-foreground tracking-tight">
                  Extraction Complete
                </h1>
              </div>
              <Button variant="outline" onClick={handleReset} className="bg-white">
                Process Another
              </Button>
            </div>
            
            <ResultsView extraction={jobStatus.result!} />
          </motion.div>
        ) : isFailed ? (
          <motion.div 
            key="error"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-20"
          >
            <div className="bg-red-50 text-red-600 p-6 rounded-2xl inline-block mb-6 border border-red-100">
              <X className="w-12 h-12 mx-auto mb-4" />
              <h2 className="text-xl font-bold mb-2">Extraction Failed</h2>
              <p className="text-sm">{jobStatus?.error || "An unexpected error occurred during processing."}</p>
            </div>
            <div>
              <Button onClick={handleReset}>Try Again</Button>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
