import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AgentTravelResponse,
  PlanItem,
  getAgentResponseText,
  getPlanItemName,
  hasRenderablePlan,
  isAgentTravelResponse,
} from './types/travel';
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

    const wrapped = parsed.reply ?? parsed.message ?? parsed.content;
    if (typeof wrapped === 'string') return parseAgentPayload(wrapped);
    if (isAgentTravelResponse(wrapped)) return wrapped;
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
    if (isAgentTravelResponse(data.reply) || isAgentTravelResponse(data.message) || isAgentTravelResponse(data.content)) {
      return JSON.stringify(data.reply || data.message || data.content);
    }
    return data.reply || data.message || data.content || '抱歉，我没有理解你的问题。';
  } catch (error) {
    console.error('Agent API failed:', error);
    return '后端暂时没有成功生成行程，请稍后重试。';
  }
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
  const [quotedItem, setQuotedItem] = useState<{
    item: PlanItem;
    dayIndex: number;
    itemIndex: number;
  } | null>(null);
  const [detailItem, setDetailItem] = useState<PlanItem | null>(null);
  const [isReplanFlow, setIsReplanFlow] = useState(false);
  const [lockKey, setLockKey] = useState(0);
  const [showSubPage, setShowSubPage] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const greetingSent = useRef(false);

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

  useEffect(() => {
    if (currentPage !== 'chat' || greetingSent.current) return;
    greetingSent.current = true;

    const greetingText = isReplanFlow
      ? '你好，我是小团☺️\n识别到你可能需要重新规划行程，可以直接告诉我航班延误、取消或想调整的内容。'
      : '你好！我是小团☺️\n听说你想规划行程～\n请告诉我你的目的地、出行天数、预算和游玩偏好，我来帮你定制专属旅行计划！';
    const msgId = uid();

    const timer = setTimeout(async () => {
      setMessages([{ role: 'agent', content: '', id: msgId }]);
      await streamReply(greetingText, msgId);
      setStreamingText('');
      setStreamingId(null);
      setMessages((prev) =>
        prev.map((message) => (message.id === msgId ? { ...message, content: greetingText } : message)),
      );
      setIsReplanFlow(false);
    }, 800);

    return () => clearTimeout(timer);
  }, [currentPage, isReplanFlow]);

  const handleActionMenu = (item: PlanItem, itemIndex: number, dayIndex: number, msgId: string) => {
    setSelectedItem({ item, itemIndex, dayIndex, msgId });
    setActionMenuVisible(true);
  };

  const updateFirstOptionDays = (
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
        return updateFirstOptionDays(message, (days) =>
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

  const handleQuote = () => {
    if (!selectedItem) return;
    setQuotedItem({
      item: selectedItem.item,
      dayIndex: selectedItem.dayIndex,
      itemIndex: selectedItem.itemIndex,
    });
    setActionMenuVisible(false);
    setSelectedItem(null);
  };

  const handleThinkingComplete = (msgId: string) => {
    setMessages((prev) =>
      prev.map((message) => (message.id === msgId ? { ...message, status: 'done' } : message)),
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

      if (structured && hasRenderablePlan(structured)) {
        setMessages((prev) => [
          ...prev,
          {
            role: 'agent',
            content: getAgentResponseText(structured),
            structured,
            id: agentId,
            status: 'thinking',
          },
        ]);
        setLoading(false);
        return;
      }

      if (structured) {
        const responseText = getAgentResponseText(structured) || '请补充目的地、日期或旅行时长，我再为你生成行程。';
        setMessages((prev) => [...prev, { role: 'agent', content: '', id: agentId }]);
        setLoading(false);
        await streamReply(responseText, agentId);
        setStreamingText('');
        setStreamingId(null);
        setMessages((prev) =>
          prev.map((message) => (message.id === agentId ? { ...message, content: responseText } : message)),
        );
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
        { role: 'agent', content: '抱歉，处理时出了点问题，请稍后再试。', id: uid() },
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

  const handleBackToLock = () => {
    setMessages([]);
    setStreamingText('');
    setStreamingId(null);
    setIsReplanFlow(true);
    greetingSent.current = false;
    setLockKey((key) => key + 1);
    setCurrentPage('lockscreen');
  };

  const handleSavePlan = async () => {
    if (loading) return;
    const replyText = '好的，已经为你保存行程。';
    const agentId = uid();
    setMessages((prev) => [...prev, { role: 'agent', content: '', id: agentId }]);
    await streamReply(replyText, agentId);
    setStreamingText('');
    setStreamingId(null);
    setMessages((prev) =>
      prev.map((message) => (message.id === agentId ? { ...message, content: replyText } : message)),
    );
  };

  const handleReplanText = async () => {
    if (loading) return;
    const replyText = '好的，请告诉我你想调整的地方，我会基于当前方案重新规划。';
    const agentId = uid();
    setMessages((prev) => [...prev, { role: 'agent', content: '', id: agentId }]);
    await streamReply(replyText, agentId);
    setStreamingText('');
    setStreamingId(null);
    setMessages((prev) =>
      prev.map((message) => (message.id === agentId ? { ...message, content: replyText } : message)),
    );
  };

  return (
    <div className="w-[430px] h-[932px] mx-auto my-4 shadow-2xl relative overflow-hidden bg-black rounded-[47px] border-[3px] border-zinc-800">
      <AnimatePresence mode="wait">
        {currentPage === 'lockscreen' && (
          <motion.div
            key={`lockscreen-${lockKey}`}
            className="absolute inset-0 z-30"
            initial={false}
            exit={{ y: '-100%', opacity: 0.5, scale: 0.96 }}
            transition={{ duration: 0.5, ease: [0.32, 0.72, 0, 1] }}
          >
            <LockScreen onEnter={() => setCurrentPage('splash')} isReplanFlow={isReplanFlow} />
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

      <AnimatePresence>
        {currentPage === 'chat' && (
          <motion.div
            key="chat"
            className="absolute inset-0 z-20"
            initial={false}
            animate={{ y: 0 }}
            exit={{ y: '30%', opacity: 0 }}
            transition={{ duration: 0.45, ease: [0.32, 0.72, 0, 1] }}
          >
            <div className="h-full flex flex-col bg-white relative overflow-hidden">
              <div className="flex items-center justify-between px-6 pt-3 pb-1 bg-white">
                <span className="text-[13px] font-medium text-black tracking-tight">
                  {new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}
                </span>
                <span className="text-[13px] font-medium text-black">5G</span>
              </div>

              <header className="flex items-center justify-between px-4 py-2 bg-white sticky top-0 z-20">
                <button onClick={handleBackToLock} className="w-10 h-10 flex items-center justify-center rounded-full bg-white shadow-[0_2px_10px_rgba(0,0,0,0.08),0_0px_2px_rgba(0,0,0,0.04)]" aria-label="Back">
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
                            <AgentThinking onComplete={() => handleThinkingComplete(message.id)} />
                          )}
                          {message.status === 'done' && message.structured && (
                            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }} className="w-full">
                              <TravelPlanCard
                                plan={message.structured}
                                onActionMenu={(item, itemIdx, dayIdx) =>
                                  handleActionMenu(item, itemIdx, dayIdx, message.id)
                                }
                                onItemTap={(item) => setDetailItem(item)}
                                onSavePlan={handleSavePlan}
                                onReplan={handleReplanText}
                                onNavigate={() => setShowSubPage(true)}
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
                      x
                    </button>
                  </motion.div>
                )}

                <form
                  onSubmit={handleSubmit}
                  className="flex items-center rounded-full bg-white shadow-[0_2px_12px_rgba(0,0,0,0.08),0_0px_2px_rgba(0,0,0,0.04)]"
                >
                  <div className="flex-1 min-w-0 max-h-[108px] overflow-y-auto">
                    <textarea
                      ref={inputRef}
                      value={input}
                      onChange={(event) => setInput(event.target.value)}
                      onKeyDown={handleKeyDown}
                      rows={1}
                      placeholder={quotedItem ? '说说你想如何调整...' : '输入你想规划的行程...'}
                      className="w-full resize-none bg-transparent pl-5 pr-2 py-3 text-[15px] text-zinc-800 placeholder-zinc-400 outline-none leading-relaxed"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={!input.trim() || loading}
                    className="w-9 h-9 flex items-center justify-center rounded-full flex-shrink-0 mr-1 transition-all duration-200 disabled:opacity-30 disabled:scale-95"
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
                onQuote={handleQuote}
                onDelete={handleDelete}
              />

              <POIDetail item={detailItem} visible={!!detailItem} onClose={() => setDetailItem(null)} />

              <AnimatePresence>
                {showSubPage && (
                  <motion.div
                    key="subpage"
                    className="absolute inset-0 z-30 bg-white"
                    initial={{ x: '100%' }}
                    animate={{ x: 0 }}
                    exit={{ x: '100%' }}
                    transition={{ duration: 0.35, ease: [0.32, 0.72, 0, 1] }}
                  >
                    <div className="flex items-center justify-between px-6 pt-3 pb-1 bg-white">
                      <span className="text-[13px] font-medium text-black tracking-tight">
                        {new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}
                      </span>
                      <span className="text-[13px] font-medium text-black">5G</span>
                    </div>
                    <header className="flex items-center px-4 py-2 bg-white">
                      <button
                        onClick={() => setShowSubPage(false)}
                        className="w-10 h-10 flex items-center justify-center rounded-full bg-white shadow-[0_2px_10px_rgba(0,0,0,0.08),0_0px_2px_rgba(0,0,0,0.04)]"
                        aria-label="Back"
                      >
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#111" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="15 18 9 12 15 6" />
                        </svg>
                      </button>
                    </header>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
