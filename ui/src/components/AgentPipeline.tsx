import { Check, Loader2, ChevronDown, XCircle, Pencil, Brain, Code, Lightbulb, Eye, BarChart3, MessageSquare, Sparkles, Bot } from 'lucide-react';
import clsx from 'clsx';
import Markdown from './Markdown';

interface PlanStep {
  index: number;
  description: string;
  task_type: string;
  agent?: string;
  backend: string;
  model: string;
  status: 'pending' | 'running' | 'done';
  result_preview?: string;
  thinking?: string;
  phase?: 'sense' | 'act' | 'reflect';
  reflectPassed?: boolean;
  reflectReason?: string;
  retrying?: boolean;
}

interface Props {
  steps: PlanStep[];
  planStatus?: 'awaiting' | 'approved' | 'rejected' | 'executing';
  onApprove: () => void;
  onReject: () => void;
  onEdit: () => void;
}

const TASK_STYLES: Record<string, { bg: string; text: string; icon: typeof Code }> = {
  coding:        { bg: 'bg-sky-500',     text: 'text-sky-400',     icon: Code },
  reasoning:     { bg: 'bg-amber-500',   text: 'text-amber-400',   icon: Brain },
  creative:      { bg: 'bg-pink-500',    text: 'text-pink-400',    icon: Sparkles },
  image:         { bg: 'bg-purple-500',  text: 'text-purple-400',  icon: Eye },
  analysis:      { bg: 'bg-indigo-500',  text: 'text-indigo-400',  icon: BarChart3 },
  chat:          { bg: 'bg-emerald-500', text: 'text-emerald-400', icon: MessageSquare },
  summarization: { bg: 'bg-teal-500',    text: 'text-teal-400',    icon: Lightbulb },
  general:       { bg: 'bg-stone-500',   text: 'text-stone-400',   icon: Bot },
};

function getStyle(taskType: string) {
  return TASK_STYLES[taskType] || TASK_STYLES.general;
}

function phaseLabel(phase: string | undefined): string {
  if (phase === 'sense') return 'Gathering context...';
  if (phase === 'act') return 'Executing...';
  if (phase === 'reflect') return 'Validating...';
  return 'Working...';
}

function AgentCard({ step }: { step: PlanStep }) {
  const style = getStyle(step.task_type);
  const Icon = style.icon;
  const isDone = step.status === 'done';
  const isRunning = step.status === 'running';

  return (
    <div className={clsx(
      'flex flex-col min-w-[190px] max-w-[220px] rounded-xl border transition-all',
      'bg-surface shadow-sm',
      isRunning
        ? 'border-blue-400/50 dark:border-blue-500/40 shadow-blue-500/10'
        : isDone
          ? 'border-emerald-300/50 dark:border-emerald-600/30'
          : 'border-border',
    )}>
      <div className="px-3.5 pt-3.5 pb-2.5">
        <div className="flex items-start gap-2.5">
          <div className={clsx(
            'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
            isDone ? 'bg-emerald-500' : style.bg,
          )}>
            {isDone
              ? <Check size={16} className="text-white" />
              : isRunning
                ? <Loader2 size={16} className="animate-spin text-white" />
                : <Icon size={16} className="text-white" />
            }
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="text-[12px] font-semibold text-primary truncate">
                {step.agent || step.task_type.charAt(0).toUpperCase() + step.task_type.slice(1)}
              </span>
            </div>
            <p className="text-[10px] text-muted leading-tight mt-0.5 line-clamp-2">
              {step.description}
            </p>
          </div>
        </div>

        <div className="mt-2.5 flex items-center gap-1.5">
          {isDone && (
            <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30
                             text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1">
              <Check size={8} /> Done
            </span>
          )}
          {isRunning && (
            <span className="text-[9px] px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30
                             text-blue-600 dark:text-blue-400 font-medium flex items-center gap-1">
              <Loader2 size={8} className="animate-spin" /> {phaseLabel(step.phase)}
            </span>
          )}
          {step.status === 'pending' && (
            <span className="text-[9px] px-2 py-0.5 rounded-full bg-stone-100 dark:bg-stone-800
                             text-stone-400 dark:text-stone-500 font-medium">
              Pending
            </span>
          )}
          {step.retrying && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30
                             text-amber-600 dark:text-amber-400 font-medium">
              Retrying
            </span>
          )}
          {isDone && step.reflectPassed !== undefined && (
            <span className={clsx(
              'text-[8px] px-1.5 py-0.5 rounded-full font-semibold',
              step.reflectPassed
                ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400'
                : 'bg-red-100 dark:bg-red-900/30 text-red-500 dark:text-red-400',
            )}>
              {step.reflectPassed ? 'PASS' : 'FAIL'}
            </span>
          )}
        </div>
      </div>

      {isDone && step.result_preview && (
        <div className="border-t border-border px-3.5 py-2.5">
          <p className="text-[10px] text-muted leading-relaxed line-clamp-3">
            {step.result_preview.slice(0, 150)}
          </p>
        </div>
      )}

      {isRunning && step.thinking && (
        <div className="border-t border-border px-3.5 py-2">
          <details className="group">
            <summary className="cursor-pointer text-[9px] text-muted font-medium flex items-center gap-1">
              <ChevronDown size={9} className="transition-transform group-open:rotate-180" />
              Chain of Thought
            </summary>
            <pre className="whitespace-pre-wrap mt-1 text-[9px] leading-relaxed text-muted italic
                            max-h-24 overflow-y-auto">
              {step.thinking}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}

export default function AgentPipeline({ steps, planStatus, onApprove, onReject, onEdit }: Props) {
  const done = steps.filter((s) => s.status === 'done').length;
  const total = steps.length;
  const allDone = done === total && total > 0;
  const isAwaiting = planStatus === 'awaiting';
  const pct = total > 0 ? (done / total) * 100 : 0;

  return (
    <div className="w-full mb-2">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Multi-Agent Pipeline
        </span>
        {isAwaiting && (
          <span className="text-[9px] px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30
                           text-amber-600 dark:text-amber-400 font-semibold animate-pulse">
            Waiting for approval
          </span>
        )}
        {planStatus === 'executing' && !allDone && (
          <span className="text-[9px] px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30
                           text-blue-600 dark:text-blue-400 font-medium flex items-center gap-1">
            <Loader2 size={8} className="animate-spin" /> Running
          </span>
        )}
        {allDone && (
          <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30
                           text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
            <Check size={8} /> Complete
          </span>
        )}
        {planStatus === 'rejected' && (
          <span className="text-[9px] px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-900/30
                           text-red-500 dark:text-red-400 font-medium">
            Rejected
          </span>
        )}
      </div>

      {/* Approval controls */}
      {isAwaiting && (
        <div className="mb-3 p-3 rounded-xl border-2 border-amber-300 dark:border-amber-700
                        bg-amber-50 dark:bg-amber-900/20">
          <p className="text-[11px] text-amber-700 dark:text-amber-300 mb-2">
            Review the pipeline. Each agent runs on a different model. Approve to proceed.
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={onApprove}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[12px] font-semibold
                         bg-emerald-600 hover:bg-emerald-700 text-white transition-colors shadow-sm"
            >
              <Check size={14} /> Approve & Run
            </button>
            <button
              onClick={onReject}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-[11px] font-medium
                         bg-stone-200 dark:bg-stone-700 text-stone-700 dark:text-stone-300
                         hover:bg-red-100 dark:hover:bg-red-900/30
                         hover:text-red-700 dark:hover:text-red-400 transition-colors"
            >
              <XCircle size={12} /> Reject
            </button>
            <button
              onClick={onEdit}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-[11px] font-medium
                         bg-stone-200 dark:bg-stone-700 text-stone-700 dark:text-stone-300
                         hover:bg-stone-300 dark:hover:bg-stone-600 transition-colors"
            >
              <Pencil size={12} /> Edit
            </button>
          </div>
        </div>
      )}

      {/* Agent cards row */}
      <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-thin">
        {steps.map((step) => (
          <AgentCard key={step.index} step={step} />
        ))}
      </div>

      {/* Progress bar */}
      {total > 0 && (
        <div className="mt-3 flex items-center gap-3">
          <div className="flex-1 h-1.5 rounded-full bg-stone-200 dark:bg-stone-700 overflow-hidden">
            <div
              className={clsx(
                'h-full rounded-full transition-all duration-500',
                allDone ? 'bg-emerald-500' : 'bg-blue-500',
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-[10px] text-muted font-medium shrink-0">
            {done}/{total}
          </span>
        </div>
      )}

      {/* Expanded results for completed steps */}
      {allDone && steps.some((s) => s.result_preview && s.result_preview.length > 150) && (
        <div className="mt-4">
          <details className="group">
            <summary className="cursor-pointer text-[11px] text-muted font-semibold uppercase tracking-wider
                               flex items-center gap-1.5 select-none mb-2">
              <ChevronDown size={12} className="transition-transform group-open:rotate-180" />
              Full Results
            </summary>
            <div className="flex flex-col gap-3 mt-1">
              {steps.filter((s) => s.result_preview).map((step) => {
                const style = getStyle(step.task_type);
                return (
                  <div key={step.index} className="border border-border rounded-lg bg-surface p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <div className={clsx('w-5 h-5 rounded-md flex items-center justify-center', style.bg)}>
                        <style.icon size={11} className="text-white" />
                      </div>
                      <span className="text-[11px] font-semibold text-primary">
                        {step.agent || step.task_type}
                      </span>
                      <span className="text-[9px] text-muted">{step.model}</span>
                    </div>
                    <div className="msg-text text-[13px] leading-[1.7]">
                      <Markdown content={step.result_preview!} />
                    </div>
                  </div>
                );
              })}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
