export type PersonaInfo = {
  author: string;
  source: string;
  index_dir: string;
  display_name: string;
  avatar_url?: string | null;
  headline: string;
  content_count?: number | null;
};

export type SourceHit = {
  rank: number;
  score: number;
  node_id: string;
  node_type: string;
  route: string;
};

export type Source = {
  rank: number;
  parent_id: string;
  score: number;
  title: string;
  path: string;
  first_hits: SourceHit[];
};

export type ChatStreamRequest = {
  author: string;
  session_id?: string | null;
  query: string;
  query_mode: 'raw' | 'grounded';
  writer_prompt: 'current' | 'strong_identity';
  parent_top_k: number;
};

export type ChatMessage = {
  role: 'user' | 'assistant' | 'error';
  text: string;
  sources?: Source[] | null;
};

export type ChatSessionSummary = {
  id: string;
  author: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type ChatSession = {
  id: string;
  author: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
};

export type ChatCallbacks = {
  onMeta?: (payload: Record<string, unknown>) => void;
  onToken?: (text: string) => void;
  onDone?: (payload: { session_id: string; answer: string; sources: Source[] }) => void;
  onError?: (message: string) => void;
};

export async function fetchPersonas(): Promise<{ personas: PersonaInfo[]; default_author?: string }> {
  const response = await fetch('/api/personas');
  if (!response.ok) {
    throw new Error(`Failed to load personas: ${response.status}`);
  }
  return response.json();
}

export async function fetchSessions(author: string): Promise<ChatSessionSummary[]> {
  const response = await fetch(`/api/personas/${encodeURIComponent(author)}/sessions`);
  if (!response.ok) {
    throw new Error(`Failed to load sessions: ${response.status}`);
  }
  const payload = await response.json();
  return payload.sessions || [];
}

export async function fetchSuggestions(author: string): Promise<string[]> {
  const response = await fetch(`/api/personas/${encodeURIComponent(author)}/suggestions`);
  if (!response.ok) {
    throw new Error(`Failed to load suggestions: ${response.status}`);
  }
  const payload = await response.json();
  return payload.suggestions || [];
}

export async function fetchSession(author: string, sessionId: string): Promise<ChatSession> {
  const response = await fetch(
    `/api/personas/${encodeURIComponent(author)}/sessions/${encodeURIComponent(sessionId)}`
  );
  if (!response.ok) {
    throw new Error(`Failed to load session: ${response.status}`);
  }
  return response.json();
}

export async function deleteSession(author: string, sessionId: string): Promise<void> {
  const response = await fetch(
    `/api/personas/${encodeURIComponent(author)}/sessions/${encodeURIComponent(sessionId)}`,
    { method: 'DELETE' }
  );
  if (!response.ok) {
    throw new Error(`Failed to delete session: ${response.status}`);
  }
}

export async function streamChat(request: ChatStreamRequest, callbacks: ChatCallbacks): Promise<void> {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  });
  if (!response.ok || !response.body) {
    throw new Error(`Chat request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    for (const part of parts) {
      dispatchSse(part, callbacks);
    }
  }
  if (buffer.trim()) {
    dispatchSse(buffer, callbacks);
  }
}

function dispatchSse(raw: string, callbacks: ChatCallbacks): void {
  const lines = raw.split('\n');
  const event = lines
    .find((line) => line.startsWith('event:'))
    ?.replace(/^event:\s*/, '')
    .trim();
  const data = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.replace(/^data:\s*/, ''))
    .join('\n');
  if (!event || !data) return;
  const payload = JSON.parse(data);
  if (event === 'meta') callbacks.onMeta?.(payload);
  if (event === 'token') callbacks.onToken?.(String(payload.text || ''));
  if (event === 'done') callbacks.onDone?.(payload);
  if (event === 'error') callbacks.onError?.(String(payload.error || 'Unknown error'));
}
