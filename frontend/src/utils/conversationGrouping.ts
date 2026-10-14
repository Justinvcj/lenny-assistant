import { SidebarSession } from '../storage/conversationStore';

export type DateGroupKey = 'pinned' | 'today' | 'yesterday' | 'previous_7_days' | 'older';

export interface ConversationGroup {
  key: DateGroupKey;
  label: string;
  conversations: SidebarSession[];
}


/**
 * Categorize a date string relative to midnight of current day.
 */
export function getDateGroupKey(dateStr: string): DateGroupKey {
  try {
    const targetDate = new Date(dateStr);
    if (isNaN(targetDate.getTime())) return 'older';

    const now = new Date();
    // Midnight today
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    // Midnight yesterday
    const startOfYesterday = new Date(startOfToday.getTime() - 24 * 60 * 60 * 1000);
    // Midnight 7 days ago
    const startOf7DaysAgo = new Date(startOfToday.getTime() - 7 * 24 * 60 * 60 * 1000);

    if (targetDate >= startOfToday) {
      return 'today';
    }
    if (targetDate >= startOfYesterday) {
      return 'yesterday';
    }
    if (targetDate >= startOf7DaysAgo) {
      return 'previous_7_days';
    }
    return 'older';
  } catch {
    return 'older';
  }
}

/**
 * Groups and filters conversations.
 * Pinned conversations are always placed in the "Pinned" group at the top.
 * Non-pinned conversations are partitioned into "Today", "Yesterday", "Previous 7 days", and "Older".
 */
export function groupConversations(
  conversations: SidebarSession[],
  searchQuery: string = ''
): ConversationGroup[] {
  const query = searchQuery.trim().toLowerCase();

  // Filter if query is provided
  const filtered = conversations.filter((c) => {
    if (!query) return true;
    if (c.title && c.title.toLowerCase().includes(query)) return true;
    if (c.messages && c.messages.some((m) => m.content && m.content.toLowerCase().includes(query))) {
      return true;
    }
    return false;
  });

  const pinned: SidebarSession[] = [];
  const today: SidebarSession[] = [];
  const yesterday: SidebarSession[] = [];
  const previous7Days: SidebarSession[] = [];
  const older: SidebarSession[] = [];


  for (const conv of filtered) {
    if (conv.pinned) {
      pinned.push(conv);
    } else {
      const groupKey = getDateGroupKey(conv.created_at || conv.updated_at);
      switch (groupKey) {
        case 'today':
          today.push(conv);
          break;
        case 'yesterday':
          yesterday.push(conv);
          break;
        case 'previous_7_days':
          previous7Days.push(conv);
          break;
        case 'older':
        default:
          older.push(conv);
          break;
      }
    }
  }

  const result: ConversationGroup[] = [];

  if (pinned.length > 0) {
    result.push({ key: 'pinned', label: 'Pinned', conversations: pinned });
  }
  if (today.length > 0) {
    result.push({ key: 'today', label: 'Today', conversations: today });
  }
  if (yesterday.length > 0) {
    result.push({ key: 'yesterday', label: 'Yesterday', conversations: yesterday });
  }
  if (previous7Days.length > 0) {
    result.push({ key: 'previous_7_days', label: 'Previous 7 days', conversations: previous7Days });
  }
  if (older.length > 0) {
    result.push({ key: 'older', label: 'Older', conversations: older });
  }

  return result;
}
