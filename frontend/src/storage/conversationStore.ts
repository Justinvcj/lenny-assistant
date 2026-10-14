import { Message, Session } from '../api';

export interface StoredConversation {

  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  pinned?: boolean;
  messages: Message[];
  llm_provider?: string;
  llm_model?: string;
}

export type SidebarSession = StoredConversation | (Session & { messages?: Message[]; pinned?: boolean });


export interface UserProfile {
  name: string;
  initials: string;
}

const STORAGE_KEY = 'lenny_conversations_v1';
const USER_PROFILE_KEY = 'lenny_user_name';

/**
 * Generate a standard UUID v4 fallback if crypto.randomUUID is not present.
 */
export function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Load all stored conversations from localStorage.
 */
export function loadStoredConversations(): StoredConversation[] {
  if (typeof window === 'undefined' || !window.localStorage) {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed;
    }
    return [];
  } catch (err) {
    console.error('Failed to load conversations from localStorage:', err);
    return [];
  }
}

/**
 * Persist conversations array into localStorage.
 */
export function saveStoredConversations(conversations: StoredConversation[]): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  } catch (err) {
    console.error('Failed to save conversations to localStorage:', err);
  }
}

/**
 * Get a single stored conversation by id.
 */
export function getStoredConversation(id: string): StoredConversation | undefined {
  const all = loadStoredConversations();
  return all.find((c) => c.id === id);
}

/**
 * Create a new stored conversation.
 */
export function createStoredConversation(title?: string, id?: string): StoredConversation {
  const all = loadStoredConversations();
  const now = new Date().toISOString();
  const newConv: StoredConversation = {
    id: id || generateUUID(),
    title: title?.trim() || 'New Chat',
    created_at: now,
    updated_at: now,
    pinned: false,
    messages: [],
  };

  const updated = [newConv, ...all.filter((c) => c.id !== newConv.id)];
  saveStoredConversations(updated);
  return newConv;
}

/**
 * Update an existing conversation.
 */
export function updateStoredConversation(
  id: string,
  updates: Partial<Omit<StoredConversation, 'id'>>
): StoredConversation | undefined {
  const all = loadStoredConversations();
  const idx = all.findIndex((c) => c.id === id);
  if (idx === -1) return undefined;

  const now = new Date().toISOString();
  const updatedItem: StoredConversation = {
    ...all[idx],
    ...updates,
    updated_at: updates.updated_at || now,
  };

  all[idx] = updatedItem;
  saveStoredConversations(all);
  return updatedItem;
}

/**
 * Delete a conversation by id.
 */
export function deleteStoredConversation(id: string): void {
  const all = loadStoredConversations();
  const filtered = all.filter((c) => c.id !== id);
  saveStoredConversations(filtered);
}

/**
 * Clear all conversations from local storage.
 */
export function clearAllStoredConversations(): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch (err) {
    console.error('Failed to clear conversations:', err);
  }
}

/**
 * Toggle pinned status of a conversation.
 */
export function togglePinConversation(id: string): boolean {
  const conv = getStoredConversation(id);
  if (!conv) return false;
  const newPinned = !conv.pinned;
  updateStoredConversation(id, { pinned: newPinned });
  return newPinned;
}

/**
 * Rename a conversation.
 */
export function renameConversation(id: string, newTitle: string): StoredConversation | undefined {
  const cleanTitle = newTitle.trim();
  if (!cleanTitle) return getStoredConversation(id);
  return updateStoredConversation(id, { title: cleanTitle });
}

/**
 * Auto-generate a title from the first user message (up to ~40 characters).
 */
export function deriveAutoTitle(userContent: string): string {
  if (!userContent) return 'New Chat';
  const clean = userContent.trim().replace(/\s+/g, ' ');
  if (clean.length <= 42) {
    return clean;
  }
  // Try breaking at word boundary near 40 chars
  const truncated = clean.slice(0, 40);
  const lastSpace = truncated.lastIndexOf(' ');
  if (lastSpace > 20) {
    return `${truncated.slice(0, lastSpace)}...`;
  }
  return `${truncated}...`;
}

/**
 * Synchronize/seed local conversations with backend sessions without overriding local edits.
 */
export function syncWithBackendSessions(backendSessions: Session[]): StoredConversation[] {
  const localConvs = loadStoredConversations();
  const localMap = new Map(localConvs.map((c) => [c.id, c]));

  let hasChanges = false;
  for (const bSession of backendSessions) {
    if (!localMap.has(bSession.id)) {
      localMap.set(bSession.id, {
        id: bSession.id,
        title: bSession.title || 'Conversation',
        created_at: bSession.created_at,
        updated_at: bSession.updated_at,
        pinned: false,
        messages: [],
      });
      hasChanges = true;
    }
  }

  const merged = Array.from(localMap.values()).sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  if (hasChanges) {
    saveStoredConversations(merged);
  }
  return merged;
}

/**
 * Export conversation to clean Markdown.
 */
export function exportConversationToMarkdown(conv: SidebarSession): string {
  const lines: string[] = [];
  lines.push(`# ${conv.title || 'Conversation'}`);
  lines.push(`_Exported on ${new Date().toLocaleString()} · ID: ${conv.id}_`);
  lines.push('');
  lines.push('---');
  lines.push('');

  const msgs = conv.messages || [];
  if (msgs.length === 0) {
    lines.push('_No messages in this conversation._');
    return lines.join('\n');
  }

  for (const msg of msgs) {
    const roleName = msg.role === 'user' ? 'User' : 'Lenny Assistant';
    lines.push(`### ${roleName}`);
    lines.push('');
    lines.push(msg.content);
    lines.push('');

    if (msg.citations && msg.citations.length > 0) {
      lines.push('**Sources:**');
      for (const cit of msg.citations) {
        const guest = cit.guest ? ` (${cit.guest})` : '';
        lines.push(`- **[S${cit.n}]** ${cit.title}${guest}`);
      }
      lines.push('');
    }
    lines.push('---');
    lines.push('');
  }

  return lines.join('\n');
}

/**
 * Export conversation to formatted JSON string.
 */
export function exportConversationToJson(conv: SidebarSession): string {
  return JSON.stringify(conv, null, 2);
}


/**
 * Export all conversations to formatted JSON string.
 */
export function exportAllConversationsToJson(): string {
  const all = loadStoredConversations();
  const exportPayload = {
    version: 1,
    exported_at: new Date().toISOString(),
    total_conversations: all.length,
    conversations: all,
  };
  return JSON.stringify(exportPayload, null, 2);
}

/**
 * Import conversations from a JSON payload string.
 */
export function importConversationsFromJson(
  jsonStr: string
): { imported: number; failed: number } {
  try {
    const data = JSON.parse(jsonStr);
    let itemsToImport: any[] = [];
    if (Array.isArray(data)) {
      itemsToImport = data;
    } else if (data && Array.isArray(data.conversations)) {
      itemsToImport = data.conversations;
    } else if (data && data.id && typeof data.title === 'string') {
      itemsToImport = [data];
    }

    if (itemsToImport.length === 0) {
      return { imported: 0, failed: 0 };
    }

    const current = loadStoredConversations();
    const currentMap = new Map(current.map((c) => [c.id, c]));
    let imported = 0;

    for (const item of itemsToImport) {
      if (item && item.id && item.title) {
        const validItem: StoredConversation = {
          id: String(item.id),
          title: String(item.title),
          created_at: item.created_at || new Date().toISOString(),
          updated_at: item.updated_at || new Date().toISOString(),
          pinned: Boolean(item.pinned),
          messages: Array.isArray(item.messages) ? item.messages : [],
        };
        currentMap.set(validItem.id, validItem);
        imported++;
      }
    }

    const merged = Array.from(currentMap.values()).sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
    saveStoredConversations(merged);
    return { imported, failed: itemsToImport.length - imported };
  } catch (err) {
    console.error('Failed to import conversations JSON:', err);
    return { imported: 0, failed: 1 };
  }
}

/**
 * Trigger a browser file download for text/json/markdown content.
 */
export function triggerFileDownload(filename: string, content: string, mimeType: string): void {
  if (typeof document === 'undefined') return;
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * User Profile helpers (display name + initials avatar).
 */
export function getUserProfile(): UserProfile {
  if (typeof window === 'undefined' || !window.localStorage) {
    return { name: 'Product Leader', initials: 'PL' };
  }
  const name = window.localStorage.getItem(USER_PROFILE_KEY) || 'Product Leader';
  const parts = name.trim().split(/\s+/);
  let initials = 'PL';
  if (parts.length >= 2) {
    initials = (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  } else if (parts.length === 1 && parts[0].length > 0) {
    initials = parts[0].slice(0, 2).toUpperCase();
  }
  return { name, initials };
}

export function saveUserProfile(name: string): UserProfile {
  const clean = name.trim() || 'Product Leader';
  if (typeof window !== 'undefined' && window.localStorage) {
    window.localStorage.setItem(USER_PROFILE_KEY, clean);
  }
  return getUserProfile();
}
