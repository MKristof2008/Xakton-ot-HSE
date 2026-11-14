export type Tab = 'check' | 'top' | 'plans' | 'history' | 'feed' | 'access';

const TABS: Tab[] = ['check', 'top', 'plans', 'history', 'feed', 'access'];

export function readTab(): Tab {
  const hash = window.location.hash.replace('#', '');
  return TABS.includes(hash as Tab) ? (hash as Tab) : 'check';
}

export function hashFor(tab: Tab): string {
  return tab === 'check' ? '' : `#${tab}`;
}
