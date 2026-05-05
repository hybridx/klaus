import { useState, useEffect, useRef, useCallback } from 'react';
import { ArrowUp, Cpu, ChevronRight, ImagePlus, X, ChevronDown, Loader2, Wrench } from 'lucide-react';
import clsx from 'clsx';
import type { WsMessage } from '../hooks/useWebSocket';
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

interface ChatMsg {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  images?: string[];
  done?: boolean;
  routing?: RoutingInfo;
  toolCall?: ToolCallInfo;
}

interface ModelOption {
  name: string;
  backend: string;
}

interface Props {
  ws: {
    connected: boolean;
    send: (d: Record<string, unknown>) => void;
    on: (fn: (m: WsMessage) => void) => () => void;
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

export default function Chat({ ws, setPage, sessionId }: Props) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [streaming, setStreaming] = useState(false);
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

  // Load conversation history on mount
  useEffect(() => {
    fetch(`/api/conversations/${sessionId}`)
      .then((r) => r.json())
      .then((data) => {
        const history: ChatMsg[] = (data.messages ?? [])
          .filter((m: { role: string }) => m.role === 'user' || m.role === 'assistant')
          .map((m: { role: string; content: string; model?: string; backend?: string }) => ({
            role: m.role as ChatMsg['role'],
            content: m.content,
            done: true,
            routing: m.model ? { model: m.model, backend: m.backend || '', reason: '' } : undefined,
          }));
        if (history.length > 0) setMessages(history);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [sessionId]);

  useEffect(() => {
    fetch('/api/models')
      .then((r) => r.json())
      .then((data) => {
        const opts: ModelOption[] = [];
        for (const [backend, backendModels] of Object.entries(data)) {
          for (const m of backendModels as Array<{ name: string }>) {
            opts.push({ name: m.name, backend });
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
      if (msg.type === 'chat.token' && currentRef.current) {
        if (pendingRoutingRef.current && !currentRef.current.routing) {
          currentRef.current.routing = pendingRoutingRef.current;
          pendingRoutingRef.current = null;
        }
        currentRef.current.content += (msg.data?.token as string) ?? '';
        setMessages((prev) => [...prev]);
        scrollBottom();
      } else if (msg.type === 'chat.done') {
        if (currentRef.current) currentRef.current.done = true;
        currentRef.current = null;
        pendingRoutingRef.current = null;
        setStreaming(false);
        setMessages((prev) => [...prev]);
      } else if (msg.type === 'chat.error') {
        if (currentRef.current) {
          currentRef.current.content += `\n[Error: ${msg.data?.error}]`;
          currentRef.current.done = true;
        }
        currentRef.current = null;
        pendingRoutingRef.current = null;
        setStreaming(false);
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
    inputRef.current!.value = '';
    inputRef.current!.style.height = 'auto';

    const payload: Record<string, unknown> = {
      type: 'chat',
      messages: [{ role: 'user', content: text || '' }],
      id: sessionId,
    };
    if (imageData.length > 0) {
      payload.images = imageData;
    }
    if (selectedModel && selectedModel.backend) {
      payload.model = selectedModel.name;
      payload.backend = selectedModel.backend;
    }

    ws.send(payload);
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

              if (m.role === 'tool') {
                const tc = m.toolCall;
                const hasResult = !!tc?.result;
                const stillRunning = !hasResult && (i === messages.length - 1 || messages[i + 1]?.role === 'tool');
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
                          <div className="truncate">{m.name}</div>
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

                {streaming && (
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
