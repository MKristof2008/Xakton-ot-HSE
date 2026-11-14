export type Tab = 'check' | 'top' | 'plans';

export function readTab(): Tab {
  const hash = window.location.hash.replace('#', '');
  return hash === 'top' || hash === 'plans' ? hash : 'check';
}

export function hashFor(tab: Tab): string {
  return tab === 'check' ? '' : `#${tab}`;
}
