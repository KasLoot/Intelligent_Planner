import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AgentTravelResponse,
  PlanItem,
  getPlanItemName,
  isAgentTravelResponse,
} from './types/travel';
import { mockTravelPlan } from './mock/travelPlan';
import AgentThinking from './components/chat/AgentThinking';
import TravelPlanCard from './components/travel/TravelPlanCard';
import ActionMenu from './components/travel/ActionMenu';
import POIDetail from './components/travel/POIDetail';
import LockScreen from './components/LockScreen';
import SplashScreen from './components/SplashScreen';

type Message = {
  role: 'user' | 'agent';
  content: string;
  structured?: AgentTravelResponse;
  id: string;
  status?: 'thinking' | 'done';
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function uid(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function parseAgentPayload(text: string): AgentTravelResponse | null {
  try {
    const parsed = JSON.parse(text);
    if (isAgentTravelResponse(parsed)) return parsed;
    if (parsed.__structured && isAgentTravelResponse(parsed.data)) return parsed.data;
  } catch {
    return null;
  }
  return null;
}

async function callAgentAPI(message: string): Promise<string> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/agent/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, timestamp: Date.now() }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`);
    }

    const data = await response.json();
    if (isAgentTravelResponse(data)) return JSON.stringify(data);
    return data.reply || data.message || data.content || '抱歉，我没有理解你的问题';
  } catch (error) {
    console.error('Agent API failed, using mock response:', error);
    return mockAgentAPI(message);
  }
}

async function mockAgentAPI(message: string): Promise<string> {
  await new Promise((resolve) => setTimeout(resolve, 600));
  const travelKeywords = ['plan', 'trip', 'travel', 'Paris', '规划', '旅行', '行程', '旅游'];
  if (travelKeywords.some((keyword) => message.includes(keyword))) {
    return JSON.stringify(mockTravelPlan);
  }
  return '你好，我是小团。可以帮你规划行程、比较交通方案，也可以根据已有方案做调整。';
}

export default function App() {
  const [currentPage, setCurrentPage] = useState<'lockscreen' | 'splash' | 'chat'>('lockscreen');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [actionMenuVisible, setActionMenuVisible] = useState(false);
  const [selectedItem, setSelectedItem] = useState<{
    item: PlanItem;
    itemIndex: number;
    dayIndex: number;
    msgId: string;
  } | null>(null);
  const [reorderMode, setReorderMode] = useState(false);
  const [reorderMsgId, setReorderMsgId] = useState<string | null>(null);
  const [quotedItem, setQuotedItem] = useState<{
    item: PlanItem;
    dayIndex: number;
    itemIndex: number;
  } | null>(null);
  const [detailItem, setDetailItem] = useState<PlanItem | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingText, loading, scrollToBottom]);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 108)}px`;
  }, [input]);

  const streamReply = async (fullText: string, msgId: string) => {
    setStreamingId(msgId);
    for (let i = 1; i <= fullText.length; i += 1) {
      setStreamingText(fullText.slice(0, i));
      await new Promise((resolve) => setTimeout(resolve, 16));
    }
  };

  const handleActionMenu = (item: PlanItem, itemIndex: number, dayIndex: number, msgId: string) => {
    setSelectedItem({ item, itemIndex, dayIndex, msgId });
    setActionMenuVisible(true);
  };

  const updateSelectedOptionDays = (
    message: Message,
    updater: (days: AgentTravelResponse['plan_options'][number]['plan']) => AgentTravelResponse['plan_options'][number]['plan'],
  ): Message => {
    if (!selectedItem || !message.structured) return message;
    const planOptions = message.structured.plan_options.map((option, optionIndex) => {
      if (optionIndex !== 0) return option;
      return { ...option, plan: updater(option.plan) };
    });
    return { ...message, structured: { ...message.structured, plan_options: planOptions } };
  };

  const handleDelete = () => {
    if (!selectedItem) return;
    setMessages((prev) =>
      prev.map((message) => {
        if (message.id !== selectedItem.msgId) return message;
        return updateSelectedOptionDays(message, (days) =>
          days.map((day, dayIndex) =>
            dayIndex === selectedItem.dayIndex
              ? { ...day, items: day.items.filter((_, itemIndex) => itemIndex !== selectedItem.itemIndex) }
              : day,
          ),
        );
      }),
    );
    setActionMenuVisible(false);
    setSelectedItem(null);
  };

  const handleMoveItem = (
    msgId: string,
    fromDay: number,
    fromIdx: number,
    toDay: number,
    toIdx: number,
  ) => {
    setMessages((prev) =>
      prev.map((message) => {
        if (message.id !== msgId || !message.structured) return message;
        const planOptions = message.structured.plan_options.map((option, optionIndex) => {
          if (optionIndex !== 0) return option;
          const days = option.plan.map((day) => ({ ...day, items: [...day.items] }));
          const [movedItem] = days[fromDay].items.splice(fromIdx, 1);
          const insertIdx = toIdx === -1 ? days[toDay].items.length : toIdx;
          days[toDay].items.splice(insertIdx, 0, movedItem);
          return { ...option, plan: days };
        });
        return { ...message, structured: { ...message.structured, plan_options: planOptions } };
      }),
    );
  };

  const send = async () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    const actualContent = quotedItem
      ? `[引用：${getPlanItemName(quotedItem.item)}] ${trimmed}`
      : trimmed;

    setMessages((prev) => [...prev, { role: 'user', content: actualContent, id: uid() }]);
    setInput('');
    setQuotedItem(null);
    setLoading(true);

    try {
      const replyText = await callAgentAPI(actualContent);
      const agentId = uid();
      const structured = parseAgentPayload(replyText);

      if (structured) {
        setMessages((prev) => [
          ...prev,
          { role: 'agent', content: structured.trip_summary, structured, id: agentId, status: 'thinking' },
        ]);
        setLoading(false);
        return;
      }

      setMessages((prev) => [...prev, { role: 'agent', content: '', id: agentId }]);
      setLoading(false);
      await streamReply(replyText, agentId);
      setStreamingText('');
      setStreamingId(null);
      setMessages((prev) =>
        prev.map((message) => (message.id === agentId ? { ...message, content: replyText } : message)),
      );
    } catch {
      setLoading(false);
      setMessages((prev) => [
        ...prev,
        { role: 'agent', content: '抱歉，出了一点问题，请稍后再试。', id: uid() },
      ]);
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    send();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  };

  const showEmpty = messages.length === 0 && !loading;

  return (
    <div className="h-full max-w-[430px] mx-auto shadow-2xl relative overflow-hidden bg-black">
      <AnimatePresence mode="wait">
        {currentPage === 'lockscreen' && (
          <motion.div
            key="lockscreen"
            className="absolute inset-0 z-30"
            initial={false}
            exit={{ y: '-100%', opacity: 0.5, scale: 0.96 }}
            transition={{ duration: 0.5, ease: [0.32, 0.72, 0, 1] }}
          >
            <LockScreen onEnter={() => setCurrentPage('splash')} />
          </motion.div>
        )}
        {currentPage === 'splash' && (
          <motion.div
            key="splash"
            className="absolute inset-0 z-30"
            initial={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
          >
            <SplashScreen onFinish={() => setCurrentPage('chat')} />
          </motion.div>
        )}
      </AnimatePresence>

      {currentPage === 'chat' && (
        <div className="h-full flex flex-col bg-white relative overflow-hidden">
          <div className="flex items-center justify-between px-6 pt-3 pb-1 bg-white">
            <span className="text-[13px] font-medium text-black tracking-tight">
              {new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}
            </span>
            <span className="text-[13px] font-medium text-black">5G</span>
          </div>

          <header className="flex items-center justify-between px-4 py-2 bg-white sticky top-0 z-20">
            <button className="w-10 h-10 flex items-center justify-center rounded-full bg-white shadow-[0_2px_10px_rgba(0,0,0,0.08),0_0px_2px_rgba(0,0,0,0.04)]" aria-label="Back">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#111" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>

            <div className="flex items-center gap-1.5">
              <img src="/xiaotuan-icon.png" alt="Xiaotuan" className="w-7 h-7 rounded-full" />
              <span className="text-[18px] font-semibold tracking-tight text-zinc-900">小团</span>
            </div>

            <button className="w-10 h-10 flex items-center justify-center rounded-full bg-white shadow-[0_2px_10px_rgba(0,0,0,0.08),0_0px_2px_rgba(0,0,0,0.04)]" aria-label="Menu">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#111" strokeWidth="2.5" strokeLinecap="round">
                <line x1="2" y1="8" x2="23" y2="8" />
                <line x1="9" y1="19" x2="23" y2="19" />
              </svg>
            </button>
          </header>

          <main className="flex-1 overflow-y-auto hide-scrollbar px-4 py-4 space-y-4">
            {showEmpty && (
              <div className="flex flex-col items-center justify-center h-full text-center px-6 -mt-8">
                <p className="text-zinc-400 text-[15px] leading-relaxed max-w-[240px]">
                  有什么可以帮你的？
                </p>
              </div>
            )}

            {messages.map((message, index) => {
              const isUser = message.role === 'user';
              const isStreaming = streamingId === message.id;
              const displayContent = isStreaming ? streamingText : message.content;
              const isStructuredMsg = message.role === 'agent' && message.structured;

              return (
                <div
                  key={message.id}
                  className={`flex ${isUser ? 'justify-end' : 'justify-start'} msg-enter`}
                  style={{ animationDelay: `${index * 0.02}s` }}
                >
                  {isStructuredMsg ? (
                    <div className="w-full">
                      {message.status === 'thinking' && (
                        <AgentThinking
                          onComplete={() =>
                            setMessages((prev) =>
                              prev.map((item) =>
                                item.id === message.id ? { ...item, status: 'done' } : item,
                              ),
                            )
                          }
                        />
                      )}

                      {message.status === 'done' && message.structured && (
                        <motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ duration: 0.4 }}
                          className="w-full"
                        >
                          <TravelPlanCard
                            plan={message.structured}
                            onActionMenu={(item, itemIdx, dayIdx) =>
                              handleActionMenu(item, itemIdx, dayIdx, message.id)
                            }
                            onItemTap={(item) => setDetailItem(item)}
                            reorderMode={reorderMode && reorderMsgId === message.id}
                            onMoveItem={(fromDay, fromIdx, toDay, toIdx) =>
                              handleMoveItem(message.id, fromDay, fromIdx, toDay, toIdx)
                            }
                            onExitReorder={() => {
                              setReorderMode(false);
                              setReorderMsgId(null);
                            }}
                          />
                        </motion.div>
                      )}
                    </div>
                  ) : (
                    <div
                      className={`max-w-[78%] px-4 py-2.5 text-[14.5px] leading-relaxed whitespace-pre-wrap break-words ${
                        isUser
                          ? 'bg-[#EDE7F6] text-zinc-800 rounded-[20px] rounded-br-[6px]'
                          : 'bg-white text-zinc-800 rounded-[20px] rounded-bl-[6px] border border-zinc-100/80'
                      } ${isStreaming ? 'caret-blink' : ''}`}
                    >
                      {displayContent || (isStreaming ? '' : '-')}
                    </div>
                  )}
                </div>
              );
            })}

            {loading && (
              <div className="flex justify-start msg-enter">
                <div className="bg-white rounded-[20px] rounded-bl-[6px] border border-zinc-100/80 px-5 py-3.5 flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-purple-300 dot-1" />
                  <span className="w-2 h-2 rounded-full bg-purple-300 dot-2" />
                  <span className="w-2 h-2 rounded-full bg-purple-300 dot-3" />
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </main>

          <div className="bg-white px-4 pt-3 pb-6">
            {quotedItem && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="flex items-center gap-2 px-4 py-2 mb-2 bg-white"
              >
                <span className="text-xs text-zinc-500 truncate">
                  引用：{getPlanItemName(quotedItem.item)}
                </span>
                <button
                  onClick={() => setQuotedItem(null)}
                  aria-label="Cancel quote"
                  className="ml-auto text-zinc-400 text-sm w-6 h-6 flex items-center justify-center rounded-full hover:bg-zinc-100"
                >
                  ×
                </button>
              </motion.div>
            )}

            <form
              onSubmit={handleSubmit}
              className="flex items-end gap-0 rounded-full overflow-hidden bg-white shadow-[0_2px_12px_rgba(0,0,0,0.08),0_0px_2px_rgba(0,0,0,0.04)]"
            >
              <textarea
                ref={inputRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                placeholder={quotedItem ? '说说你想如何调整…' : '输入你想问的…'}
                className="flex-1 resize-none bg-transparent px-5 py-2.5 text-[15px] text-zinc-800 placeholder-zinc-400 outline-none leading-relaxed max-h-[108px]"
              />

              <button
                type="submit"
                disabled={!input.trim() || loading}
                className="w-9 h-9 flex items-center justify-center rounded-full flex-shrink-0 mr-1.5 mb-0.5 transition-all duration-200 disabled:opacity-30 disabled:scale-95"
                style={{
                  background: input.trim() && !loading
                    ? 'linear-gradient(135deg, #7C3AED, #8B5CF6)'
                    : '#e5e7eb',
                }}
                aria-label="Send"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </form>
          </div>

          <ActionMenu
            visible={actionMenuVisible}
            onClose={() => {
              setActionMenuVisible(false);
              setSelectedItem(null);
            }}
            onQuote={() => {
              if (selectedItem) {
                setQuotedItem({
                  item: selectedItem.item,
                  dayIndex: selectedItem.dayIndex,
                  itemIndex: selectedItem.itemIndex,
                });
              }
              setActionMenuVisible(false);
              setSelectedItem(null);
            }}
            onDelete={handleDelete}
            onReorder={() => {
              if (selectedItem) {
                setReorderMode(true);
                setReorderMsgId(selectedItem.msgId);
              }
              setActionMenuVisible(false);
              setSelectedItem(null);
            }}
          />

          <POIDetail
            item={detailItem}
            visible={!!detailItem}
            onClose={() => setDetailItem(null)}
          />
        </div>
      )}
    </div>
  );
}
