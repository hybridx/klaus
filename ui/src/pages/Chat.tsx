import { useState, useEffect, useRef, useCallback } from 'react';
import { ArrowUp, Cpu, ChevronRight, ImagePlus, X, ChevronDown, Loader2, Wrench, Check, XCircle, Pencil, Bot } from 'lucide-react';
import clsx from 'clsx';
import type { SSEMessage } from '../hooks/useEventStream';
import { postChat, postPlanAction } from '../hooks/useEventStream';
import type { Page } from '../App';
import Markdown from '../components/Markdown';

interface RoutingInfo {
  backend: string;
  model: string;
  reason: string;
}

interface ImageAttachment {
  file: File;
  preview: string;
  base64: string;
}

interface ToolCallInfo {
  name: string;
  args: Record<string, unknown>;
  result?: string;
}

interface SubtaskInfo {
  index: number;
  text: string;
  task: string;
  backend: string;
  model: string;
}

interface PlanStepInfo {
  index: number;
  description: string;
  task_type: string;
  agent?: string;
  backend: string;
  model: string;
  status: 'pending' | 'running' | 'done';
  result_preview?: string;
}

interface ChatMsg {
  role: 'user' | 'assistant' | 'system' | 'tool' | 'subtask-divider' | 'plan';
  content: string;
  images?: string[];
  done?: boolean;
  routing?: RoutingInfo;
  toolCall?: ToolCallInfo;
  subtask?: SubtaskInfo;
  planSteps?: PlanStepInfo[];
  planStatus?: 'awaiting' | 'approved' | 'rejected' | 'executing';
  planAgents?: Array<{ name: string; description: string; capabilities: string[] }>;
}

interface ModelOption {
  name: string;
  backend: string;
  capabilities?: string[];
}

interface Props {
  ws: {
    connected: boolean;
    on: (fn: (m: SSEMessage) => void) => () => void;
  };
  setPage: (p: Page) => void;
  sessionId: string;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.split(',')[1]);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

interface StatusStep {
  step: string;
  detail: string;
  ts: number;
}

const STATUS_ICONS: Record<string, string> = {
  classifying: '🔍',
  classified: '🏷️',
  splitting: '✂️',
  routing: '🔀',
  routed: '✅',
  memory: '🧠',
  generating: '⚡',
  saving: '💾',
  tool: '🔧',
  tool_done: '✅',
};

export default function Chat({ ws, setPage, sessionId }: Props) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [statusSteps, setStatusSteps] = useState<StatusStep[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [selectedModel, setSelectedModel] = useState<ModelOption | null>({ name: 'Auto', backend: '' });
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [images, setImages] = useState<ImageAttachment[]>([]);
  const [loaded, setLoaded] = useState(false);
  const currentRef = useRef<ChatMsg | null>(null);
  const pendingRoutingRef = useRef<RoutingInfo | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const modelPickerRef = useRef<HTMLDivElement>(null);

  // Load conversation history on mount — auto-retry if last msg was user (interrupted generation)
  const pendingRetryRef = useRef<string | null>(null);

  useEffect(() => {
    fetch(`/api/conversations/${sessionId}`)
      .then((r) => r.json())
      .then((data) => {
        const raw = (data.messages ?? []).filter(
          (m: { role: string }) => m.role === 'user' || m.role === 'assistant',
        );
        const history: ChatMsg[] = raw.map(
          (m: { role: string; content: string; model?: string; backend?: string }) => ({
            role: m.role as ChatMsg['role'],
            content: m.content,
            done: true,
            routing: m.model ? { model: m.model, backend: m.backend || '', reason: '' } : undefined,
          }),
        );

        if (history.length > 0) {
          const last = raw[raw.length - 1];
          if (last.role === 'user') {
            const assistant: ChatMsg = { role: 'assistant', content: '', done: false };
            currentRef.current = assistant;
            setMessages([...history, assistant]);
            setStreaming(true);
            pendingRetryRef.current = last.content;
          } else {
            setMessages(history);
          }
        }
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [sessionId]);

  // When WS connects and there's a pending retry, re-send the last user message
  const retrySent = useRef(false);
  useEffect(() => {
    if (retrySent.current) return;

    const trySend = () => {
      if (!pendingRetryRef.current) return;
      const text = pendingRetryRef.current;
      pendingRetryRef.current = null;
      retrySent.current = true;

      postChat({
        messages: [{ role: 'user', content: text }],
        id: sessionId,
        retry: true,
      }).catch(console.error);
    };

    if (ws.connected && pendingRetryRef.current) {
      trySend();
      return;
    }

    return ws.on((msg) => {
      if (msg.type === '_connected') {
        setTimeout(trySend, 100);
      }
    });
  }, [ws, sessionId]);

  useEffect(() => {
    fetch('/api/models')
      .then((r) => r.json())
      .then((data) => {
        const opts: ModelOption[] = [];
        for (const [backend, backendModels] of Object.entries(data)) {
          for (const m of backendModels as Array<{ name: string; capabilities?: string[] }>) {
            opts.push({ name: m.name, backend, capabilities: m.capabilities });
          }
        }
        setModels(opts);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (modelPickerRef.current && !modelPickerRef.current.contains(e.target as Node)) {
        setShowModelPicker(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const scrollBottom = useCallback(() => {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    });
  }, []);

  useEffect(() => {
    return ws.on((msg) => {
      if (msg.type === 'chat.status' && msg.data?.chat_id) {
        const d = msg.data;
        setStatusSteps((prev) => [
          ...prev,
          { step: d.step as string, detail: d.detail as string, ts: Date.now() },
        ]);
        scrollBottom();
      } else if (msg.type === 'chat.token' && currentRef.current) {
        if (pendingRoutingRef.current && !currentRef.current.routing) {
          currentRef.current.routing = pendingRoutingRef.current;
          pendingRoutingRef.current = null;
        }
        currentRef.current.content += (msg.data?.token as string) ?? '';
        setStatusSteps([]);
        setMessages((prev) => [...prev]);
        scrollBottom();
      } else if (msg.type === 'chat.done') {
        if (currentRef.current) currentRef.current.done = true;
        currentRef.current = null;
        pendingRoutingRef.current = null;
        setStreaming(false);
        setStatusSteps([]);
        setMessages((prev) => [...prev]);
      } else if (msg.type === 'chat.error') {
        if (currentRef.current) {
          currentRef.current.content += `\n[Error: ${msg.data?.error}]`;
          currentRef.current.done = true;
        }
        currentRef.current = null;
        pendingRoutingRef.current = null;
        setStreaming(false);
        setStatusSteps([]);
        setMessages((prev) => [...prev]);
      } else if (msg.type === 'model.routed' && msg.data?.chat_id) {
        const d = msg.data;
        const info: RoutingInfo = {
          backend: d.backend as string,
          model: (d.model as string) || 'default',
          reason: (d.reason as string) || '',
        };
        if (currentRef.current) {
          currentRef.current.routing = info;
          setMessages((prev) => [...prev]);
        } else {
          pendingRoutingRef.current = info;
        }
        scrollBottom();
      } else if (msg.type === 'mcp.tool_called' && msg.data?.chat_id) {
        const d = msg.data;
        setMessages((prev) => [
          ...prev,
          {
            role: 'tool',
            content: d.name as string,
            toolCall: {
              name: d.name as string,
              args: (d.args as Record<string, unknown>) ?? {},
            },
          },
        ]);
        scrollBottom();
      } else if (msg.type === 'tool.result' && msg.data?.chat_id) {
        const d = msg.data;
        setMessages((prev) => {
          const copy = [...prev];
          for (let j = copy.length - 1; j >= 0; j--) {
            if (copy[j].role === 'tool' && copy[j].toolCall?.name === d.name && !copy[j].toolCall?.result) {
              copy[j] = {
                ...copy[j],
                toolCall: { ...copy[j].toolCall!, result: d.content as string },
              };
              break;
            }
          }
          return copy;
        });
        scrollBottom();
      } else if (msg.type === 'subtask.start' && msg.data?.chat_id) {
        const d = msg.data;
        const subtaskInfo: SubtaskInfo = {
          index: d.index as number,
          text: d.text as string,
          task: d.task as string,
          backend: d.backend as string,
          model: d.model as string,
        };
        if (currentRef.current) {
          currentRef.current.done = true;
        }
        const assistant: ChatMsg = { role: 'assistant', content: '', done: false };
        currentRef.current = assistant;
        pendingRoutingRef.current = null;
        setMessages((prev) => {
          const cleaned = prev.filter(
            (m) => !(m.role === 'assistant' && !m.done && !m.content),
          );
          return [
            ...cleaned,
            { role: 'subtask-divider', content: '', subtask: subtaskInfo },
            assistant,
          ];
        });
        scrollBottom();
      } else if (msg.type === 'subtask.done' && msg.data?.chat_id) {
        if (currentRef.current) {
          currentRef.current.done = true;
        }
        currentRef.current = null;
        setMessages((prev) => [...prev]);
      } else if (msg.type === 'plan.created' && msg.data?.chat_id) {
        const plan = (msg.data.plan as Array<{
          index: number; description: string; task_type: string;
          agent?: string; backend: string; model: string;
        }>).map((s) => ({
          ...s,
          status: 'pending' as const,
        }));
        const agents = (msg.data.agents || []) as Array<{
          name: string; description: string; capabilities: string[];
        }>;
        setStatusSteps([]);
        setMessages((prev) => {
          const cleaned = prev.filter(
            (m) => !(m.role === 'assistant' && !m.done && !m.content),
          );
          return [...cleaned, { role: 'plan', content: '', planSteps: plan, planAgents: agents }];
        });
        scrollBottom();
      } else if (msg.type === 'plan.awaiting_approval' && msg.data?.chat_id) {
        setMessages((prev) => {
          const copy = [...prev];
          const planMsg = copy.find((m) => m.role === 'plan');
          if (planMsg) planMsg.planStatus = 'awaiting';
          return copy;
        });
        scrollBottom();
      } else if (msg.type === 'plan.approved' && msg.data?.chat_id) {
        setMessages((prev) => {
          const copy = [...prev];
          const planMsg = copy.find((m) => m.role === 'plan');
          if (planMsg) planMsg.planStatus = 'executing';
          return copy;
        });
      } else if (msg.type === 'plan.rejected' && msg.data?.chat_id) {
        setMessages((prev) => {
          const copy = [...prev];
          const planMsg = copy.find((m) => m.role === 'plan');
          if (planMsg) planMsg.planStatus = 'rejected';
          return copy;
        });
      } else if (msg.type === 'plan.revised' && msg.data?.chat_id) {
        const newPlan = (msg.data.plan as Array<{
          index: number; description: string; task_type: string;
          agent?: string; backend: string; model: string;
        }>).map((s) => ({
          ...s,
          status: 'pending' as const,
        }));
        setMessages((prev) => {
          const copy = [...prev];
          const planMsg = copy.find((m) => m.role === 'plan');
          if (planMsg) {
            planMsg.planSteps = newPlan;
            planMsg.planStatus = 'executing';
          }
          return copy;
        });
      } else if (msg.type === 'plan.step_start' && msg.data?.chat_id) {
        const idx = msg.data.index as number;
        setMessages((prev) => {
          const copy = [...prev];
          const planMsg = copy.find((m) => m.role === 'plan');
          if (planMsg) {
            planMsg.planStatus = 'executing';
            if (planMsg.planSteps) {
              planMsg.planSteps = planMsg.planSteps.map((s) =>
                s.index === idx ? { ...s, status: 'running' as const } : s,
              );
            }
          }
          return copy;
        });
        scrollBottom();
      } else if (msg.type === 'plan.step_done' && msg.data?.chat_id) {
        const idx = msg.data.index as number;
        const preview = (msg.data.result_preview as string) || '';
        setMessages((prev) => {
          const copy = [...prev];
          const planMsg = copy.find((m) => m.role === 'plan');
          if (planMsg?.planSteps) {
            planMsg.planSteps = planMsg.planSteps.map((s) =>
              s.index === idx ? { ...s, status: 'done' as const, result_preview: preview } : s,
            );
          }
          return copy;
        });
        scrollBottom();
      } else if (msg.type === 'plan.consolidated' && msg.data?.chat_id) {
        const assistant: ChatMsg = { role: 'assistant', content: '', done: false };
        currentRef.current = assistant;
        setMessages((prev) => [...prev, assistant]);
        scrollBottom();
      }
    });
  }, [ws, scrollBottom]);

  const addImages = useCallback(async (files: FileList | File[]) => {
    const attachments: ImageAttachment[] = [];
    for (const f of Array.from(files)) {
      if (!f.type.startsWith('image/')) continue;
      const base64 = await fileToBase64(f);
      attachments.push({ file: f, preview: URL.createObjectURL(f), base64 });
    }
    setImages((prev) => [...prev, ...attachments]);
  }, []);

  const removeImage = useCallback((idx: number) => {
    setImages((prev) => {
      const next = [...prev];
      URL.revokeObjectURL(next[idx].preview);
      next.splice(idx, 1);
      return next;
    });
  }, []);

  const send = () => {
    const text = inputRef.current?.value.trim();
    if ((!text && images.length === 0) || streaming) return;

    const imageData = images.map((img) => img.base64);
    const imagePreviews = images.map((img) => img.preview);

    const assistant: ChatMsg = { role: 'assistant', content: '', done: false };
    currentRef.current = assistant;
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text || '', images: imagePreviews.length > 0 ? imagePreviews : undefined },
      assistant,
    ]);
    setStreaming(true);
    setStatusSteps([]);
    inputRef.current!.value = '';
    inputRef.current!.style.height = 'auto';

    postChat({
      messages: [{ role: 'user', content: text || '' }],
      id: sessionId,
      images: imageData.length > 0 ? imageData : undefined,
      model: selectedModel?.backend ? selectedModel.name : undefined,
      backend: selectedModel?.backend || undefined,
    }).catch(console.error);

    setImages([]);
    scrollBottom();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
    const ta = e.target as HTMLTextAreaElement;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 96) + 'px';
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files.length > 0) addImages(e.dataTransfer.files);
  }, [addImages]);

  const onPaste = useCallback((e: React.ClipboardEvent) => {
    const items = e.clipboardData.items;
    const files: File[] = [];
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        const f = item.getAsFile();
        if (f) files.push(f);
      }
    }
    if (files.length > 0) addImages(files);
  }, [addImages]);

  // Scroll to bottom after loading history
  useEffect(() => {
    if (loaded && messages.length > 0) scrollBottom();
  }, [loaded]);

  const empty = messages.length === 0;

  return (
    <div className="flex flex-col h-full" onDrop={onDrop} onDragOver={(e) => e.preventDefault()}>
      <div ref={scrollRef} className={clsx(
        'flex-1 overflow-y-auto',
        empty && 'flex items-center justify-center',
      )}>
        {empty ? (
          <div className="flex flex-col items-center gap-3 px-6 -mt-12">
            <div className="text-[22px] font-semibold tracking-tight text-stone-700 dark:text-stone-300">
              What can I help with?
            </div>
            {selectedModel && (
              <div className="text-[12px] text-stone-400 dark:text-stone-500">
                {selectedModel.backend
                  ? <>Using <span className="font-medium">{selectedModel.name}</span> on {selectedModel.backend}</>
                  : <>Using <span className="font-medium">Auto</span> routing</>
                }
              </div>
            )}
          </div>
        ) : (
          <div className="max-w-[640px] mx-auto px-6 py-6 flex flex-col gap-5">
            {messages.map((m, i) => {
              if (m.role === 'system') return null;

              if (m.role === 'subtask-divider' && m.subtask) {
                const st = m.subtask;
                return (
                  <div key={i} className="flex items-center gap-2 py-1">
                    <div className="flex-1 h-px bg-stone-200 dark:bg-stone-700" />
                    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full
                                    bg-stone-100 dark:bg-stone-800 border border-stone-200 dark:border-stone-700">
                      <span className="text-[10px] font-semibold uppercase tracking-wider
                                       text-stone-500 dark:text-stone-400">
                        {st.task}
                      </span>
                      <span className="text-[10px] text-stone-400 dark:text-stone-500">
                        {st.model} on {st.backend}
                      </span>
                    </div>
                    <div className="flex-1 h-px bg-stone-200 dark:bg-stone-700" />
                  </div>
                );
              }

              if (m.role === 'plan' && m.planSteps) {
                const isAwaiting = m.planStatus === 'awaiting';
                return (
                  <div key={i} className="max-w-[90%] mb-2">
                    <div className="flex items-center gap-2 mb-1.5">
                      <div className="text-[10px] font-semibold uppercase tracking-wider
                                      text-stone-400 dark:text-stone-500">
                        Execution Plan
                      </div>
                      {isAwaiting && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 font-medium">
                          Awaiting approval
                        </span>
                      )}
                      {m.planStatus === 'executing' && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 font-medium flex items-center gap-1">
                          <Loader2 size={8} className="animate-spin" /> Executing
                        </span>
                      )}
                      {m.planStatus === 'rejected' && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 font-medium">
                          Rejected
                        </span>
                      )}
                    </div>
                    <div className="border border-border rounded-lg bg-surface overflow-hidden divide-y divide-border">
                      {m.planSteps.map((step) => (
                        <div key={step.index} className="flex items-start gap-2 px-3 py-2">
                          <div className="mt-0.5 shrink-0">
                            {step.status === 'done' && (
                              <span className="text-[11px] text-emerald-500">&#10003;</span>
                            )}
                            {step.status === 'running' && (
                              <Loader2 size={11} className="animate-spin text-amber-500" />
                            )}
                            {step.status === 'pending' && (
                              <span className="inline-block w-2.5 h-2.5 rounded-full border border-stone-300 dark:border-stone-600" />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className={clsx(
                              'text-[12px]',
                              step.status === 'done'
                                ? 'text-stone-500 dark:text-stone-400'
                                : step.status === 'running'
                                  ? 'text-stone-800 dark:text-stone-200 font-medium'
                                  : 'text-stone-400 dark:text-stone-600',
                            )}>
                              {step.description}
                            </div>
                            <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                              <span className="text-[9px] px-1.5 py-0.5 rounded-full
                                               bg-stone-100 dark:bg-stone-800
                                               text-stone-500 dark:text-stone-400 uppercase font-semibold">
                                {step.task_type}
                              </span>
                              {step.agent && (
                                <span className="text-[9px] px-1.5 py-0.5 rounded-full
                                                 bg-violet-100 dark:bg-violet-900/30
                                                 text-violet-600 dark:text-violet-400 font-medium flex items-center gap-0.5">
                                  <Bot size={8} /> {step.agent}
                                </span>
                              )}
                              <span className="text-[9px] text-stone-400 dark:text-stone-500">
                                {step.model} on {step.backend}
                              </span>
                            </div>
                            {step.status === 'done' && step.result_preview && (
                              <p className="text-[10px] text-stone-400 dark:text-stone-500 mt-1 line-clamp-2">
                                {step.result_preview}
                              </p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                    {/* Approval controls */}
                    {isAwaiting && (
                      <div className="mt-2 flex items-center gap-2">
                        <button
                          onClick={() => postPlanAction(sessionId, 'approve').catch(console.error)}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium
                                     bg-emerald-600 hover:bg-emerald-700 text-white transition-colors"
                        >
                          <Check size={12} /> Approve
                        </button>
                        <button
                          onClick={() => {
                            const reason = prompt('Why reject this plan?') || '';
                            postPlanAction(sessionId, 'reject', { reason }).catch(console.error);
                          }}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium
                                     bg-red-600 hover:bg-red-700 text-white transition-colors"
                        >
                          <XCircle size={12} /> Reject
                        </button>
                        <button
                          onClick={() => {
                            const raw = prompt(
                              'Edit plan (JSON array of edits):\n'
                              + 'e.g. [{"index": 0, "description": "new description"}, {"index": 2, "remove": true}]'
                            );
                            if (!raw) return;
                            try {
                              const edits = JSON.parse(raw);
                              const reason = prompt('Why this change?') || '';
                              postPlanAction(sessionId, 'edit', { edits, reason }).catch(console.error);
                            } catch {
                              alert('Invalid JSON');
                            }
                          }}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium
                                     bg-stone-600 hover:bg-stone-700 text-white transition-colors"
                        >
                          <Pencil size={12} /> Edit
                        </button>
                      </div>
                    )}
                  </div>
                );
              }

              if (m.role === 'tool') {
                const tc = m.toolCall;
                const hasResult = !!tc?.result;
                const stillRunning = !hasResult && streaming;
                return (
                  <div key={i} className="flex items-start gap-2.5 max-w-[90%]">
                    <div className={clsx(
                      'mt-0.5 shrink-0 w-5 h-5 rounded-md flex items-center justify-center',
                      hasResult
                        ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400'
                        : 'bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400',
                    )}>
                      {stillRunning
                        ? <Loader2 size={12} className="animate-spin" />
                        : <Wrench size={11} />
                      }
                    </div>
                    <div className="flex flex-col gap-0.5 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className={clsx(
                          'text-[12px] font-semibold',
                          hasResult
                            ? 'text-emerald-700 dark:text-emerald-400'
                            : 'text-amber-700 dark:text-amber-400',
                        )}>
                          {tc?.name ?? m.content}
                        </span>
                        {stillRunning && (
                          <span className="text-[10px] text-stone-400 dark:text-stone-500 italic">
                            running...
                          </span>
                        )}
                        {hasResult && (
                          <span className="text-[10px] text-emerald-500 dark:text-emerald-600">
                            done
                          </span>
                        )}
                      </div>
                      <details className="group/args">
                        <summary className="text-[10px] text-stone-400 dark:text-stone-500 cursor-pointer
                                           hover:text-stone-600 dark:hover:text-stone-300 select-none
                                           list-none flex items-center gap-1">
                          <ChevronRight size={10} className="transition-transform group-open/args:rotate-90" />
                          details
                        </summary>
                        <div className="mt-1 space-y-1">
                          {tc && Object.keys(tc.args).length > 0 && (
                            <div>
                              <div className="text-[9px] uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-0.5 font-medium">
                                Input
                              </div>
                              <pre className="text-[10px] leading-snug font-mono whitespace-pre-wrap break-all
                                              text-stone-500 dark:text-stone-400 bg-stone-50 dark:bg-stone-800/50
                                              rounded-md px-2 py-1.5 max-h-[120px] overflow-y-auto">
                                {JSON.stringify(tc.args, null, 2)}
                              </pre>
                            </div>
                          )}
                          {tc?.result && (
                            <div>
                              <div className="text-[9px] uppercase tracking-wider text-stone-400 dark:text-stone-500 mb-0.5 font-medium">
                                Output
                              </div>
                              <pre className="text-[10px] leading-snug font-mono whitespace-pre-wrap break-all
                                              text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20
                                              rounded-md px-2 py-1.5 max-h-[120px] overflow-y-auto">
                                {tc.result}
                              </pre>
                            </div>
                          )}
                        </div>
                      </details>
                    </div>
                  </div>
                );
              }

              if (m.role === 'user') {
                return (
                  <div key={i} className="flex flex-col items-end gap-2">
                    {m.images && m.images.length > 0 && (
                      <div className="flex flex-wrap gap-2 max-w-[85%] justify-end">
                        {m.images.map((src, j) => (
                          <img key={j} src={src} alt=""
                               className="max-h-[160px] max-w-[200px] rounded-xl object-cover
                                          border border-stone-200 dark:border-stone-700" />
                        ))}
                      </div>
                    )}
                    <div className="text-[14px] leading-relaxed whitespace-pre-wrap break-words
                                    px-4 py-2.5 rounded-3xl rounded-br-lg max-w-[85%]
                                    bg-stone-100 dark:bg-stone-800 text-stone-800 dark:text-stone-200">
                      {m.content}
                    </div>
                  </div>
                );
              }

              return (
                <div key={i} className="flex flex-col gap-1.5">
                  {m.routing && (
                    <button
                      onClick={() => setPage('routing')}
                      className="group inline-flex items-center gap-1 self-start
                                 text-[10px] text-stone-500 dark:text-stone-500
                                 hover:text-stone-700 dark:hover:text-stone-300 transition-colors"
                      title="View routing rules"
                    >
                      <Cpu size={9} />
                      <span className="font-medium">{m.routing.model}</span>
                      <span className="opacity-40">on {m.routing.backend}</span>
                      <ChevronRight size={8} className="opacity-0 group-hover:opacity-60 transition-opacity" />
                    </button>
                  )}
                  {!m.done && !m.content && streaming && statusSteps.length > 0 && (
                    <div className="flex flex-col gap-1 mb-2">
                      {statusSteps.map((s, si) => {
                        const isLatest = si === statusSteps.length - 1;
                        return (
                          <div key={si} className={clsx(
                            'flex items-center gap-1.5 text-[11px] transition-opacity duration-300',
                            isLatest
                              ? 'text-stone-600 dark:text-stone-300'
                              : 'text-stone-400 dark:text-stone-600',
                          )}>
                            <span className="text-[10px]">
                              {STATUS_ICONS[s.step] || '⏳'}
                            </span>
                            <span className={clsx(isLatest && 'animate-pulse')}>
                              {s.detail}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  <div className="msg-text text-[14px] leading-[1.75] break-words">
                    <Markdown content={m.content} />
                    {!m.done && (
                      <span className="inline-block w-[2px] h-[15px] bg-stone-400 dark:bg-stone-500
                                       rounded-full animate-pulse ml-0.5 align-text-bottom" />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Input ── */}
      <div className="shrink-0 pb-5 pt-2 px-4">
        <div className="max-w-[640px] mx-auto">
          {/* Image previews */}
          {images.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2 px-1">
              {images.map((img, idx) => (
                <div key={idx} className="relative group">
                  <img src={img.preview} alt=""
                       className="h-16 w-16 rounded-lg object-cover border border-stone-200 dark:border-stone-700" />
                  <button
                    onClick={() => removeImage(idx)}
                    className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full
                               bg-stone-800 dark:bg-stone-200 text-white dark:text-stone-900
                               flex items-center justify-center opacity-0 group-hover:opacity-100
                               transition-opacity shadow-sm"
                  >
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="bg-surface border border-border rounded-2xl px-4 py-3
                          shadow-sm focus-within:shadow-md focus-within:border-stone-300
                          dark:focus-within:border-stone-600 transition-all">
            <textarea
              ref={inputRef}
              rows={1}
              placeholder={empty ? 'Ask anything...' : 'Write a message...'}
              onKeyDown={onKey}
              onPaste={onPaste}
              className="w-full bg-transparent text-[14px] leading-snug resize-none
                         min-h-[22px] max-h-[96px] outline-none
                         text-stone-900 dark:text-stone-100
                         placeholder:text-stone-400 dark:placeholder:text-stone-500"
            />
            <div className="flex items-center justify-between mt-2">
              <div className="flex items-center gap-2">
                {/* Model selector */}
                <div className="relative" ref={modelPickerRef}>
                  <button
                    onClick={() => setShowModelPicker(!showModelPicker)}
                    className="flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg
                               text-stone-500 dark:text-stone-400
                               hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                  >
                    <span className="max-w-[120px] truncate">
                      {selectedModel?.name || 'Auto'}
                    </span>
                    <ChevronDown size={10} />
                  </button>
                  {showModelPicker && models.length > 0 && (
                    <div className="absolute bottom-full left-0 mb-1 w-56
                                    bg-surface border border-border rounded-xl shadow-lg
                                    py-1 max-h-60 overflow-y-auto z-50">
                      <button
                        onClick={() => { setSelectedModel({ name: 'Auto', backend: '' }); setShowModelPicker(false); }}
                        className={clsx(
                          'w-full text-left px-3 py-1.5 text-[12px] transition-colors',
                          'hover:bg-stone-100 dark:hover:bg-stone-800',
                          !selectedModel?.backend
                            ? 'text-stone-900 dark:text-stone-100 font-medium'
                            : 'text-stone-600 dark:text-stone-400',
                        )}
                      >
                        <div>Auto</div>
                        <div className="text-[10px] text-stone-400 dark:text-stone-500">use routing rules</div>
                      </button>
                      <div className="h-px bg-border mx-2 my-1" />
                      {models.map((m, idx) => (
                        <button
                          key={idx}
                          onClick={() => { setSelectedModel(m); setShowModelPicker(false); }}
                          className={clsx(
                            'w-full text-left px-3 py-1.5 text-[12px] transition-colors',
                            'hover:bg-stone-100 dark:hover:bg-stone-800',
                            selectedModel?.name === m.name && selectedModel?.backend === m.backend
                              ? 'text-stone-900 dark:text-stone-100 font-medium'
                              : 'text-stone-600 dark:text-stone-400',
                          )}
                        >
                          <div className="flex items-center gap-1 truncate">
                            <span>{m.name}</span>
                            {m.capabilities && !m.capabilities.includes('tools') && (
                              <span className="text-[9px] px-1 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40
                                               text-amber-600 dark:text-amber-400 leading-none shrink-0"
                                    title="This model does not support tool calling">
                                no tools
                              </span>
                            )}
                          </div>
                          <div className="text-[10px] text-stone-400 dark:text-stone-500">{m.backend}</div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Image upload */}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  className="hidden"
                  onChange={(e) => { if (e.target.files) addImages(e.target.files); e.target.value = ''; }}
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="p-1 rounded-lg text-stone-400 dark:text-stone-500
                             hover:text-stone-600 dark:hover:text-stone-300
                             hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                  title="Attach image"
                >
                  <ImagePlus size={15} />
                </button>

                {streaming && statusSteps.length > 0 && (
                  <span className="text-[10px] text-stone-400 dark:text-stone-500 animate-pulse flex items-center gap-1">
                    <span>{STATUS_ICONS[statusSteps[statusSteps.length - 1].step] || '⏳'}</span>
                    {statusSteps[statusSteps.length - 1].detail}
                  </span>
                )}
                {streaming && statusSteps.length === 0 && (
                  <span className="text-[10px] text-stone-400 dark:text-stone-500 animate-pulse">
                    Thinking...
                  </span>
                )}
              </div>

              <button
                onClick={send}
                disabled={streaming}
                className={clsx(
                  'w-7 h-7 flex items-center justify-center rounded-full transition-all',
                  streaming
                    ? 'bg-stone-100 dark:bg-stone-800 text-stone-300 dark:text-stone-600'
                    : 'bg-stone-800 dark:bg-stone-200 text-white dark:text-stone-900 hover:opacity-80',
                )}
              >
                <ArrowUp size={14} strokeWidth={2.5} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
