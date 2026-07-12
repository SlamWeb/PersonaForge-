import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Check, Copy, Plus, Settings2, Trash2 } from 'lucide-react';
import {
  ChatSessionSummary,
  deleteSession,
  fetchPersonas,
  fetchSession,
  fetchSessions,
  fetchSuggestions,
  PersonaInfo,
  Source,
  streamChat
} from './api';

type Message = {
  id: string;
  role: 'user' | 'assistant' | 'error';
  text: string;
  sources?: Source[] | null;
};

const USER_AVATAR = '你';
const OPENING_LINE = '今天想聊点什么？';

export default function App() {
  const [personas, setPersonas] = useState<PersonaInfo[]>([]);
  const [author, setAuthor] = useState('');
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [queryMode, setQueryMode] = useState<'raw' | 'grounded'>('grounded');
  const [writerPrompt, setWriterPrompt] = useState<'current' | 'strong_identity'>('strong_identity');
  const [parentTopK, setParentTopK] = useState(20);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState('Loading local personas...');
  const [busy, setBusy] = useState(false);

  const selectedPersona = useMemo(
    () => personas.find((item) => item.author === author) || null,
    [personas, author]
  );
  const canSend = useMemo(() => Boolean(author && input.trim() && !busy), [author, input, busy]);

  useEffect(() => {
    fetchPersonas()
      .then((payload) => {
        setPersonas(payload.personas);
        const selected = payload.default_author || payload.personas[0]?.author || '';
        setAuthor(selected);
        setStatus(selected ? `Ready: ${selected}` : 'No local persona index found.');
      })
      .catch((error) => {
        setStatus(String(error.message || error));
      });
  }, []);

  useEffect(() => {
    if (!author) return;
    refreshSessions(author);
    refreshSuggestions(author);
    setCurrentSessionId(null);
    setMessages([]);
  }, [author]);

  async function refreshSessions(targetAuthor = author) {
    if (!targetAuthor) return;
    try {
      setSessions(await fetchSessions(targetAuthor));
    } catch (error) {
      setStatus(String((error as Error).message || error));
    }
  }

  async function refreshSuggestions(targetAuthor = author) {
    if (!targetAuthor) return;
    try {
      setSuggestions(await fetchSuggestions(targetAuthor));
    } catch {
      setSuggestions([]);
    }
  }

  async function openSession(sessionId: string) {
    if (!author || busy) return;
    try {
      const session = await fetchSession(author, sessionId);
      setCurrentSessionId(session.id);
      setMessages(
        session.messages.map((message) => ({
          id: makeId(),
          role: message.role,
          text: message.text,
          sources: message.sources
        }))
      );
      setStatus(`Ready: ${author}`);
    } catch (error) {
      setStatus(String((error as Error).message || error));
    }
  }

  async function removeSession(sessionId: string) {
    if (!author || busy) return;
    await deleteSession(author, sessionId);
    if (currentSessionId === sessionId) {
      newChat();
    }
    await refreshSessions(author);
  }

  function newChat() {
    setCurrentSessionId(null);
    setMessages([]);
    setInput('');
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || !author) return;

    const userId = makeId();
    const assistantId = makeId();
    setMessages((items) => [
      ...items,
      { id: userId, role: 'user', text },
      { id: assistantId, role: 'assistant', text: '' }
    ]);
    setInput('');
    setBusy(true);
    setStatus('Retrieving and generating...');

    try {
      await streamChat(
        {
          author,
          session_id: currentSessionId,
          query: text,
          query_mode: queryMode,
          writer_prompt: writerPrompt,
          parent_top_k: parentTopK
        },
        {
          onMeta: (payload) => {
            const sessionId = String(payload.session_id || '');
            if (sessionId) setCurrentSessionId(sessionId);
            setStatus('Streaming answer...');
          },
          onToken: (token) => {
            setMessages((items) =>
              items.map((message) =>
                message.id === assistantId ? { ...message, text: message.text + token } : message
              )
            );
          },
          onDone: async (payload) => {
            setCurrentSessionId(payload.session_id);
            setMessages((items) =>
              items.map((message) =>
                message.id === assistantId
                  ? { ...message, text: payload.answer || message.text, sources: payload.sources }
                  : message
              )
            );
            setStatus(`Ready: ${author}`);
            await refreshSessions(author);
          },
          onError: (message) => {
            throw new Error(message);
          }
        }
      );
    } catch (error) {
      setMessages((items) => [
        ...items.filter((message) => message.id !== assistantId),
        { id: makeId(), role: 'error', text: String((error as Error).message || error) }
      ]);
      setStatus('Error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <PersonaPicker personas={personas} author={author} onAuthorChange={setAuthor} selectedPersona={selectedPersona} />

        <button className="new-chat-button" type="button" onClick={newChat}>
          <Plus size={16} />
          新对话
        </button>

        <section className="session-section">
          <div className="section-label">历史对话</div>
          <div className="session-list">
            {sessions.length === 0 ? (
              <div className="muted-empty">暂无历史会话</div>
            ) : (
              sessions.map((session) => (
                <div className={`session-item ${session.id === currentSessionId ? 'active' : ''}`} key={session.id}>
                  <button className="session-open" type="button" onClick={() => openSession(session.id)}>
                    <span>{session.title}</span>
                    <small>{session.message_count} 条消息</small>
                  </button>
                  <button
                    className="delete-session"
                    type="button"
                    title="删除会话"
                    onClick={() => removeSession(session.id)}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))
            )}
          </div>
        </section>

        <details className="advanced-settings">
          <summary>
            <Settings2 size={15} />
            检索与生成设置
          </summary>
          <div className="control-grid">
            <label>
              RAG
              <select value={queryMode} onChange={(event) => setQueryMode(event.target.value as 'raw' | 'grounded')}>
                <option value="grounded">Grounded</option>
                <option value="raw">Raw</option>
              </select>
            </label>
            <label>
              TopK
              <input
                type="number"
                min={1}
                max={40}
                value={parentTopK}
                onChange={(event) => setParentTopK(Number(event.target.value) || 20)}
              />
            </label>
          </div>

          <label>
            Writer
            <select
              value={writerPrompt}
              onChange={(event) => setWriterPrompt(event.target.value as 'current' | 'strong_identity')}
            >
              <option value="strong_identity">Strong Identity</option>
              <option value="current">Current</option>
            </select>
          </label>
        </details>

        <div className="sidebar-footer">
          <span>PersonaForge</span>
          <span>{status === 'Error' ? '出现错误' : busy ? '生成中' : '本地运行中'}</span>
        </div>
      </aside>

      <main className="chat-panel">
        <section className="messages">
          {messages.length === 0 ? (
            <OpeningMessage persona={selectedPersona} />
          ) : (
            messages.map((message) => (
              <ChatBubble key={message.id} message={message} persona={selectedPersona} />
            ))
          )}
        </section>

        <div className="composer-area">
          {messages.length === 0 && suggestions.length ? (
            <SuggestionChips suggestions={suggestions} onPickSuggestion={setInput} />
          ) : null}
          <form className="composer" onSubmit={handleSubmit}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="例如：如何看待女生常说的配得感？"
            />
            <button type="submit" disabled={!canSend}>
              {busy ? '生成中' : '发送'}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}

function PersonaPicker({
  personas,
  author,
  selectedPersona,
  onAuthorChange
}: {
  personas: PersonaInfo[];
  author: string;
  selectedPersona: PersonaInfo | null;
  onAuthorChange: (author: string) => void;
}) {
  return (
    <section className="persona-card">
      <Avatar label={selectedPersona?.display_name || author || 'PF'} src={selectedPersona?.avatar_url || undefined} />
      <div className="persona-main">
        <select value={author} onChange={(event) => onAuthorChange(event.target.value)}>
          {personas.map((item) => (
            <option key={item.author} value={item.author}>
              {item.display_name || item.author}
            </option>
          ))}
        </select>
      </div>
    </section>
  );
}

function OpeningMessage({ persona }: { persona: PersonaInfo | null }) {
  return (
    <div className="opening-wrap">
      <article className="chat-row from-persona opening-message">
        <Avatar label={persona?.display_name || 'PF'} src={persona?.avatar_url || undefined} />
        <div className="bubble-stack">
          <div className="chat-bubble">
            <div className="message-text">{OPENING_LINE}</div>
          </div>
        </div>
      </article>
    </div>
  );
}

function SuggestionChips({
  suggestions,
  onPickSuggestion
}: {
  suggestions: string[];
  onPickSuggestion: (question: string) => void;
}) {
  return (
    <div className="suggestion-list" aria-label="建议问题">
      {suggestions.slice(0, 4).map((item) => (
        <button className="suggestion-chip" type="button" key={item} onClick={() => onPickSuggestion(item)}>
          {item}
        </button>
      ))}
    </div>
  );
}

function ChatBubble({ message, persona }: { message: Message; persona: PersonaInfo | null }) {
  const isUser = message.role === 'user';
  const isError = message.role === 'error';
  return (
    <article className={`chat-row ${isUser ? 'from-user' : 'from-persona'} ${isError ? 'error' : ''}`}>
      {!isUser ? <Avatar label={persona?.display_name || 'PF'} src={persona?.avatar_url || undefined} /> : null}
      <div className="bubble-stack">
        <div className="chat-bubble">
          <CopyButton text={message.text} />
          <div className="message-text">{message.text || (message.role === 'assistant' ? '...' : '')}</div>
          {message.sources ? <Sources sources={message.sources} /> : null}
        </div>
      </div>
      {isUser ? <Avatar label={USER_AVATAR} /> : null}
    </article>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  }
  return (
    <button className="copy-button" type="button" title="复制" onClick={copy}>
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

function Avatar({ label, src }: { label: string; src?: string }) {
  const initials = label.trim().slice(0, 2).toUpperCase() || 'PF';
  if (src) {
    return <img className="avatar" src={src} alt={label} />;
  }
  return <div className="avatar avatar-fallback">{initials}</div>;
}

function Sources({ sources }: { sources: Source[] }) {
  return (
    <details className="sources">
      <summary>引用了 {sources.length} 篇历史材料</summary>
      <div className="source-list">
        {sources.map((source) => (
          <div className="source-card" key={`${source.rank}-${source.parent_id}`}>
            <div className="source-title">
              {source.rank}. {source.title || source.parent_id}
            </div>
            <div className="source-meta">{source.path}</div>
            <details className="technical-source">
              <summary>技术详情</summary>
              <div className="source-meta">{source.parent_id}</div>
              <div className="hit-list">
                {source.first_hits.map((hit) => (
                  <span key={`${hit.route}-${hit.rank}-${hit.node_id}`}>
                    {hit.route} #{hit.rank} {hit.node_type}
                  </span>
                ))}
              </div>
            </details>
          </div>
        ))}
      </div>
    </details>
  );
}

function makeId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
