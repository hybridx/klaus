import { useState, useEffect, useRef, useCallback } from 'react';
import { ArrowUp, Cpu, ChevronRight, ImagePlus, X, ChevronDown, Loader2, Wrench, Check, XCircle, Pencil, Bot, Circle, CircleDot, CircleCheck, ArrowUpCircle, Trash2 } from 'lucide-react';
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
  thinking?: string;
  phase?: 'sense' | 'act' | 'reflect';
  reflectPassed?: boolean;
  reflectReason?: string;
  retrying?: boolean;
}

interface ChatMsg {
  role: 'user' | 'assistant' | 'system' | 'tool' | 'subtask-divider' | 'plan';
  content: string;
  images?: string[];
  done?: boolean;
  routing?: RoutingInfo;
  toolCall?: ToolCallInfo;
  subtask?: SubtaskInfo;
  thinking?: string;
  planSteps?: PlanStepInfo[];
  planStatus?: 'awaiting' | 'approved' | 'rejected' | 'executing';
  planAgents?: Array<{ name: string; description: string; capabilities: string[] }>;
}

interface QueueItem {
  id: string;
  text: string;
  images: ImageAttachment[];
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
  status: 'pending' | 'in_progress' | 'completed';
}

const STEP_DONE_MAP: Record<string, string> = {
  classifying: 'classified',
  splitting: 'split',
  routing: 'routed',
  generating: 'generated',
  saving: 'saved',
  tool: 'tool_done',
};

const STEP_ORDER = ['classifying', 'splitting', 'routing', 'memory', 'generating', 'saving'];

function buildTodoSteps(rawSteps: StatusStep[]): StatusStep[] {
  const seen = new Map<string, StatusStep>();
  for (const s of rawSteps) {
    const baseStep = Object.entries(STEP_DONE_MAP).find(([, done]) => done === s.step)?.[0];
    if (baseStep && seen.has(baseStep)) {
      seen.get(baseStep)!.status = 'completed';
      continue;
    }
    if (!seen.has(s.step)) {
      seen.set(s.step, { ...s, status: 'in_progress' });
    }
  }

  const entries = Array.from(seen.values());
  for (let i = 0; i < entries.length - 1; i++) {
    if (entries[i].status === 'in_progress') entries[i].status = 'completed';
  }
  return entries;
}

export default function Chat({ ws, setPage, sessionId }: Props) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [statusSteps, setStatusSteps] = useState<StatusStep[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [selectedModel, setSelectedModel] = useState<ModelOption | null>({ name: 'Auto', backend: '' });
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [images, setImages] = useState<ImageAttachment[]>([]);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [showQueue, setShowQueue] = useState(true);
  const [editingQueueId, setEditingQueueId] = useState<string | null>(null);
  const [editingQueueText, setEditingQueueText] = useState('');
  const [loaded, setLoaded] = useState(false);
  const currentRef = useRef<ChatMsg | null>(null);
  const pendingRoutingRef = useRef<RoutingInfo | null>(null);
  const queueDrainRef = useRef(false);
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
          { step: d.step as string, detail: d.detail as string, ts: Date.now(), status: 'in_progress' as const },
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
        queueDrainRef.current = true;
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
        const result = (msg.data.result as string) || (msg.data.result_preview as string) || '';
        const model = (msg.data.model as string) || '';
        const backend = (msg.data.backend as string) || '';
        const taskType = (msg.data.task_type as string) || '';
        setMessages((prev) => {
          const copy = [...prev];
          const planMsg = copy.find((m) => m.role === 'plan');
          if (planMsg?.planSteps) {
            planMsg.planSteps = planMsg.planSteps.map((s) =>
              s.index === idx ? {
                ...s,
                status: 'done' as const,
                result_preview: result,
                model: model || s.model,
                backend: backend || s.backend,
                task_type: taskType || s.task_type,
              } : s,
            );
          }
          return copy;
        });
        scrollBottom();
      } else if (msg.type === 'thinking' && msg.data?.chat_id) {
        const thinkContent = msg.data.content as string;
        setMessages((prev) => {
          const copy = [...prev];
          const last = copy.findLast((m) => m.role === 'assistant');
          if (last) {
            last.thinking = (last.thinking || '') + thinkContent;
          }
          return copy;
        });
      } else if (msg.type === 'plan.phase' && msg.data?.chat_id) {
        const idx = msg.data.index as number;
        const phase = msg.data.phase as PlanStepInfo['phase'];
        setMessages((prev) => {
          const copy = [...prev];
          const planMsg = copy.find((m) => m.role === 'plan');
          if (planMsg?.planSteps) {
            planMsg.planSteps = planMsg.planSteps.map((s) =>
              s.index === idx ? { ...s, phase } : s,
            );
          }
          return copy;
        });
      } else if (msg.type === 'plan.step_thinking' && msg.data?.chat_id) {
        const idx = msg.data.index as number;
        const content = msg.data.content as string;
        setMessages((prev) => {
          const copy = [...prev];
          const planMsg = copy.find((m) => m.role === 'plan');
          if (planMsg?.planSteps) {
            planMsg.planSteps = planMsg.planSteps.map((s) =>
              s.index === idx ? { ...s, thinking: (s.thinking || '') + content } : s,
            );
          }
          return copy;
        });
      } else if (msg.type === 'plan.step_reflect' && msg.data?.chat_id) {
        const idx = msg.data.index as number;
        const reflectPassed = msg.data.passed as boolean;
        const reflectReason = msg.data.reason as string;
        const retrying = msg.data.retrying as boolean;
        setMessages((prev) => {
          const copy = [...prev];
          const planMsg = copy.find((m) => m.role === 'plan');
          if (planMsg?.planSteps) {
            planMsg.planSteps = planMsg.planSteps.map((s) =>
              s.index === idx ? {
                ...s,
                reflectPassed,
                reflectReason,
                retrying,
              } : s,
            );
          }
          return copy;
        });
      }
    });
  }, [ws, scrollBottom]);

  const removeFromQueue = useCallback((id: string) => {
    setQueue((prev) => prev.filter((q) => q.id !== id));
  }, []);

  const promoteInQueue = useCallback((id: string) => {
    setQueue((prev) => {
      const idx = prev.findIndex((q) => q.id === id);
      if (idx <= 0) return prev;
      const copy = [...prev];
      [copy[idx - 1], copy[idx]] = [copy[idx], copy[idx - 1]];
      return copy;
    });
  }, []);

  const saveQueueEdit = useCallback((id: string) => {
    setQueue((prev) => prev.map((q) =>
      q.id === id ? { ...q, text: editingQueueText } : q,
    ));
    setEditingQueueId(null);
    setEditingQueueText('');
  }, [editingQueueText]);

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

  const sendDirect = useCallback((text: string, attachedImages: ImageAttachment[]) => {
    const imageData = attachedImages.map((img) => img.base64);
    const imagePreviews = attachedImages.map((img) => img.preview);

    const assistant: ChatMsg = { role: 'assistant', content: '', done: false };
    currentRef.current = assistant;
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text, images: imagePreviews.length > 0 ? imagePreviews : undefined },
      assistant,
    ]);
    setStreaming(true);
    setStatusSteps([]);

    postChat({
      messages: [{ role: 'user', content: text }],
      id: sessionId,
      images: imageData.length > 0 ? imageData : undefined,
      model: selectedModel?.backend ? selectedModel.name : undefined,
      backend: selectedModel?.backend || undefined,
    }).catch(console.error);

    scrollBottom();
  }, [sessionId, selectedModel, scrollBottom]);

  useEffect(() => {
    if (!queueDrainRef.current || streaming) return;
    queueDrainRef.current = false;
    if (queue.length === 0) return;

    const [next, ...rest] = queue;
    setQueue(rest);
    setTimeout(() => sendDirect(next.text, next.images), 150);
  }, [streaming, queue, sendDirect]);

  const send = () => {
    const text = inputRef.current?.value.trim();
    if (!text && images.length === 0) return;

    const currentImages = [...images];
    inputRef.current!.value = '';
    inputRef.current!.style.height = 'auto';
    setImages([]);

    if (streaming) {
      setQueue((prev) => [...prev, {
        id: Date.now().toString(),
        text: text || '',
        images: currentImages,
      }]);
      return;
    }

    sendDirect(text || '', currentImages);
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
                const allDone = m.planSteps.every((s) => s.status === 'done');
                return (
                  <div key={i} className="w-full mb-2">
                    {/* Plan header */}
                    <div className="flex items-center gap-2 mb-2">
                      <div className="text-[11px] font-semibold uppercase tracking-wider
                                      text-stone-500 dark:text-stone-400">
                        Plan
                      </div>
                      {isAwaiting && (
                        <span className="text-[9px] px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 font-semibold animate-pulse">
                          Waiting for your approval
                        </span>
                      )}
                      {m.planStatus === 'executing' && !allDone && (
                        <span className="text-[9px] px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 font-medium flex items-center gap-1">
                          <Loader2 size={8} className="animate-spin" /> Running
                        </span>
                      )}
                      {allDone && (
                        <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 font-medium">
                          Complete
                        </span>
                      )}
                      {m.planStatus === 'rejected' && (
                        <span className="text-[9px] px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 font-medium">
                          Rejected
                        </span>
                      )}
                    </div>

                    {/* Approval controls — prominent when awaiting */}
                    {isAwaiting && (
                      <div className="mb-3 p-3 rounded-lg border-2 border-amber-300 dark:border-amber-700
                                      bg-amber-50 dark:bg-amber-900/20">
                        <p className="text-[11px] text-amber-700 dark:text-amber-300 mb-2">
                          Review the plan below. Each step runs on a different model. Approve to proceed, or reject/edit.
                        </p>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => postPlanAction(sessionId, 'approve').catch(console.error)}
                            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[12px] font-semibold
                                       bg-emerald-600 hover:bg-emerald-700 text-white transition-colors shadow-sm"
                          >
                            <Check size={14} /> Approve & Run
                          </button>
                          <button
                            onClick={() => {
                              const reason = prompt('Why reject this plan?') || '';
                              postPlanAction(sessionId, 'reject', { reason }).catch(console.error);
                            }}
                            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-[11px] font-medium
                                       bg-stone-200 dark:bg-stone-700 text-stone-700 dark:text-stone-300
                                       hover:bg-red-100 dark:hover:bg-red-900/30
                                       hover:text-red-700 dark:hover:text-red-400 transition-colors"
                          >
                            <XCircle size={12} /> Reject
                          </button>
                          <button
                            onClick={() => {
                              const raw = prompt(
                                'Edit plan (JSON array of edits):\n'
                                + 'e.g. [{"index": 0, "description": "new desc"}, {"index": 2, "remove": true}]'
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
                            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-[11px] font-medium
                                       bg-stone-200 dark:bg-stone-700 text-stone-700 dark:text-stone-300
                                       hover:bg-stone-300 dark:hover:bg-stone-600 transition-colors"
                          >
                            <Pencil size={12} /> Edit
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Steps as TODO list */}
                    <div className="flex flex-col gap-3">
                      {m.planSteps.map((step) => (
                        <div key={step.index} className={clsx(
                          'border rounded-lg overflow-hidden transition-colors',
                          step.status === 'running'
                            ? 'border-blue-300 dark:border-blue-700 bg-blue-50/50 dark:bg-blue-900/10'
                            : step.status === 'done'
                              ? 'border-emerald-200 dark:border-emerald-800 bg-surface'
                              : 'border-border bg-surface',
                        )}>
                          {/* Step header */}
                          <div className="flex items-center gap-2.5 px-3 py-2.5">
                            <div className="shrink-0">
                              {step.status === 'done' && (
                                <div className="w-5 h-5 rounded-md bg-emerald-500 flex items-center justify-center">
                                  <Check size={12} className="text-white" />
                                </div>
                              )}
                              {step.status === 'running' && (
                                <div className="w-5 h-5 rounded-md bg-blue-500 flex items-center justify-center">
                                  <Loader2 size={12} className="animate-spin text-white" />
                                </div>
                              )}
                              {step.status === 'pending' && (
                                <div className="w-5 h-5 rounded-md border-2 border-stone-300 dark:border-stone-600" />
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className={clsx(
                                'text-[12px] leading-tight',
                                step.status === 'done'
                                  ? 'text-stone-600 dark:text-stone-300'
                                  : step.status === 'running'
                                    ? 'text-stone-800 dark:text-stone-100 font-semibold'
                                    : 'text-stone-500 dark:text-stone-500',
                              )}>
                                {step.description}
                              </div>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0">
                              <span className={clsx(
                                'text-[9px] px-1.5 py-0.5 rounded-md font-semibold uppercase',
                                step.task_type === 'image'
                                  ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400'
                                  : step.task_type === 'coding'
                                    ? 'bg-sky-100 dark:bg-sky-900/30 text-sky-600 dark:text-sky-400'
                                    : step.task_type === 'creative'
                                      ? 'bg-pink-100 dark:bg-pink-900/30 text-pink-600 dark:text-pink-400'
                                      : 'bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400',
                              )}>
                                {step.task_type}
                              </span>
                              {step.agent && (
                                <span className="text-[9px] px-1.5 py-0.5 rounded-md
                                                 bg-violet-100 dark:bg-violet-900/30
                                                 text-violet-600 dark:text-violet-400 font-medium flex items-center gap-0.5">
                                  <Bot size={8} /> {step.agent}
                                </span>
                              )}
                              <span className="text-[9px] font-medium text-stone-400 dark:text-stone-500">
                                {step.model}
                              </span>
                            </div>
                          </div>

                          {/* Phase indicator */}
                          {step.status === 'running' && step.phase && (
                            <div className="border-t border-border px-3 py-1.5 flex items-center gap-1.5">
                              <Loader2 size={10} className="animate-spin text-blue-400" />
                              <span className="text-[10px] font-medium text-blue-400 uppercase tracking-wider">
                                {step.phase === 'sense' && 'Gathering context...'}
                                {step.phase === 'act' && 'Executing...'}
                                {step.phase === 'reflect' && 'Validating output...'}
                              </span>
                            </div>
                          )}

                          {/* Reflect retry indicator */}
                          {step.retrying && (
                            <div className="border-t border-border px-3 py-1.5 flex items-center gap-1.5 bg-amber-50/50 dark:bg-amber-900/10">
                              <Loader2 size={10} className="animate-spin text-amber-500" />
                              <span className="text-[10px] text-amber-600 dark:text-amber-400">
                                Output failed validation ({step.reflectReason}) &mdash; retrying...
                              </span>
                            </div>
                          )}

                          {/* Thinking / reasoning (collapsible) */}
                          {step.thinking && (
                            <div className="border-t border-border px-3 py-2">
                              <details className="group">
                                <summary className="cursor-pointer text-[10px] text-stone-400 dark:text-stone-500 font-medium flex items-center gap-1">
                                  <ChevronDown size={10} className="transition-transform group-open:rotate-180" />
                                  Chain of Thought
                                </summary>
                                <pre className="whitespace-pre-wrap mt-1.5 text-[11px] leading-relaxed text-stone-400 dark:text-stone-500 italic max-h-48 overflow-y-auto">
                                  {step.thinking}
                                </pre>
                              </details>
                            </div>
                          )}

                          {/* Step result — shown inline when done */}
                          {step.status === 'done' && step.result_preview && (
                            <div className="border-t border-border px-3 py-2.5">
                              <div className="flex items-center gap-1.5 mb-1.5">
                                <Cpu size={9} className="text-stone-400" />
                                <span className="text-[9px] font-medium text-stone-400 dark:text-stone-500">
                                  {step.model} on {step.backend}
                                </span>
                                {step.reflectPassed !== undefined && (
                                  <span className={clsx(
                                    'text-[8px] px-1 py-0.5 rounded font-medium',
                                    step.reflectPassed
                                      ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400'
                                      : 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400',
                                  )}>
                                    {step.reflectPassed ? 'PASS' : `FAIL: ${step.reflectReason}`}
                                  </span>
                                )}
                              </div>
                              <div className="msg-text text-[13px] leading-[1.7]">
                                <Markdown content={step.result_preview} />
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
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
                  {!m.done && !m.content && streaming && statusSteps.length > 0 && (() => {
                    const todos = buildTodoSteps(statusSteps);
                    return (
                      <div className="mb-3 border border-stone-200 dark:border-stone-700 rounded-xl
                                      bg-white dark:bg-stone-800/60 shadow-sm overflow-hidden max-w-[380px]">
                        <div className="flex items-center gap-2 px-3 py-2 border-b border-stone-100 dark:border-stone-700/60">
                          <CircleDot size={14} className="text-stone-500 dark:text-stone-400" />
                          <span className="text-[12px] font-semibold text-stone-700 dark:text-stone-300">
                            To-dos
                          </span>
                          <span className="text-[11px] text-stone-400 dark:text-stone-500 font-medium">
                            {todos.length}
                          </span>
                        </div>
                        <div className="flex flex-col py-1">
                          {todos.map((s, si) => (
                            <div key={si} className="flex items-center gap-2.5 px-3 py-1.5">
                              {s.status === 'completed' && (
                                <CircleCheck size={16} className="text-emerald-500 dark:text-emerald-400 shrink-0" />
                              )}
                              {s.status === 'in_progress' && (
                                <Loader2 size={16} className="animate-spin text-blue-500 dark:text-blue-400 shrink-0" />
                              )}
                              {s.status === 'pending' && (
                                <Circle size={16} className="text-stone-300 dark:text-stone-600 shrink-0" />
                              )}
                              <span className={clsx(
                                'text-[12px] leading-tight',
                                s.status === 'completed' && 'text-stone-400 dark:text-stone-500 line-through',
                                s.status === 'in_progress' && 'text-stone-700 dark:text-stone-200 font-medium',
                                s.status === 'pending' && 'text-stone-400 dark:text-stone-500',
                              )}>
                                {s.detail}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })()}
                  {m.thinking && (
                    <details className="mb-2 group">
                      <summary className="cursor-pointer text-[10px] text-stone-400 dark:text-stone-500
                                         font-medium flex items-center gap-1 select-none">
                        <ChevronDown size={10} className="transition-transform group-open:rotate-180" />
                        Chain of Thought
                      </summary>
                      <pre className="whitespace-pre-wrap mt-1.5 text-[11px] leading-relaxed
                                      text-stone-400 dark:text-stone-500 italic
                                      max-h-48 overflow-y-auto border-l-2 border-stone-200
                                      dark:border-stone-700 pl-3 ml-1">
                        {m.thinking}
                      </pre>
                    </details>
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

          {/* Queue widget */}
          {queue.length > 0 && (
            <div className="mb-2 border border-stone-200 dark:border-stone-700 rounded-xl
                            bg-white dark:bg-stone-800/60 shadow-sm overflow-hidden">
              <button
                onClick={() => setShowQueue(!showQueue)}
                className="w-full flex items-center gap-2 px-3 py-2
                           hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
              >
                <ChevronDown size={14} className={clsx(
                  'text-stone-400 dark:text-stone-500 transition-transform',
                  !showQueue && '-rotate-90',
                )} />
                <span className="text-[12px] font-semibold text-stone-600 dark:text-stone-300">
                  {queue.length} Queued
                </span>
              </button>

              {showQueue && (
                <div className="border-t border-stone-100 dark:border-stone-700/60">
                  {queue.map((item, idx) => (
                    <div
                      key={item.id}
                      className="flex items-start gap-2.5 px-3 py-2
                                 border-b border-stone-50 dark:border-stone-700/40 last:border-b-0
                                 hover:bg-stone-50 dark:hover:bg-stone-800/40 transition-colors group"
                    >
                      <Circle size={16} className="text-stone-300 dark:text-stone-600 shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        {editingQueueId === item.id ? (
                          <div className="flex items-center gap-1.5">
                            <input
                              autoFocus
                              value={editingQueueText}
                              onChange={(e) => setEditingQueueText(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') saveQueueEdit(item.id);
                                if (e.key === 'Escape') setEditingQueueId(null);
                              }}
                              className="flex-1 text-[12px] bg-transparent border border-stone-200
                                         dark:border-stone-600 rounded px-2 py-1
                                         text-stone-800 dark:text-stone-200
                                         focus:outline-none focus:ring-1 focus:ring-blue-400"
                            />
                            <button
                              onClick={() => saveQueueEdit(item.id)}
                              className="p-1 text-emerald-500 hover:text-emerald-600 transition-colors"
                            >
                              <Check size={14} />
                            </button>
                            <button
                              onClick={() => setEditingQueueId(null)}
                              className="p-1 text-stone-400 hover:text-stone-600 transition-colors"
                            >
                              <X size={14} />
                            </button>
                          </div>
                        ) : (
                          <span className="text-[12px] text-stone-600 dark:text-stone-300 line-clamp-2">
                            {item.text}
                            {item.images.length > 0 && (
                              <span className="text-[10px] text-stone-400 ml-1">
                                +{item.images.length} image{item.images.length > 1 ? 's' : ''}
                              </span>
                            )}
                          </span>
                        )}
                      </div>
                      {editingQueueId !== item.id && (
                        <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={() => { setEditingQueueId(item.id); setEditingQueueText(item.text); }}
                            className="p-1 text-stone-400 hover:text-stone-600
                                       dark:hover:text-stone-300 transition-colors rounded"
                            title="Edit"
                          >
                            <Pencil size={13} />
                          </button>
                          {idx > 0 && (
                            <button
                              onClick={() => promoteInQueue(item.id)}
                              className="p-1 text-stone-400 hover:text-blue-500
                                         transition-colors rounded"
                              title="Move up"
                            >
                              <ArrowUpCircle size={13} />
                            </button>
                          )}
                          <button
                            onClick={() => removeFromQueue(item.id)}
                            className="p-1 text-stone-400 hover:text-red-500
                                       transition-colors rounded"
                            title="Remove"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
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

                {streaming && statusSteps.length > 0 && (() => {
                  const todos = buildTodoSteps(statusSteps);
                  const active = todos.find((t) => t.status === 'in_progress');
                  return (
                    <span className="text-[10px] text-stone-500 dark:text-stone-400 flex items-center gap-1.5">
                      <Loader2 size={10} className="animate-spin text-blue-500" />
                      {active?.detail || 'Processing...'}
                    </span>
                  );
                })()}
                {streaming && statusSteps.length === 0 && (
                  <span className="text-[10px] text-stone-400 dark:text-stone-500 flex items-center gap-1.5">
                    <Loader2 size={10} className="animate-spin" />
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
