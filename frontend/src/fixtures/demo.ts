import type { Deal, Listing, Offer, OfferCheck, SignalResult, Stats, Trust } from '../types';

/**
 * Демо-набор «Свидетель». Используется ТОЛЬКО в режиме demo
 * (VITE_API_MODE=demo) и всегда помечается бейджем «демо» в интерфейсе.
 * В live-режиме эти данные не подставляются ни при каких ошибках.
 */

const now = Date.now();
const hoursAgo = (h: number): string => new Date(now - h * 3600_000).toISOString();

export const DEMO_TRUST: Trust = {
  score: 84,
  uncertainty: 0.12,
  coverage: 0.9,
  level: 'confirmed',
  conflict: false,
};

export const DEMO_SIGNALS: SignalResult[] = [
  {
    id: 'exif',
    name: 'Метаданные (EXIF)',
    stage: 'provenance',
    verdict: 'supports_real',
    strength: 0.92,
    reliability: 0.95,
    summary: 'EXIF цел: камера, дата и GPS согласуются между собой.',
    details: {
      camera: 'iPhone 14 Pro',
      lens: 'Main Camera 24mm',
      software: 'iOS 17.2',
      gps_present: true,
    },
  },
  {
    id: 'c2pa',
    name: 'Манифест C2PA',
    stage: 'provenance',
    verdict: 'neutral',
    strength: 0.3,
    reliability: 0.7,
    summary: 'Манифеста подписи нет — частый случай для мобильных камер.',
    details: {},
  },
  {
    id: 'ai_detector',
    name: 'Следы генерации',
    stage: 'artifacts',
    verdict: 'supports_real',
    strength: 0.81,
    reliability: 0.78,
    summary: 'Ансамбль детекторов не нашёл характерных артефактов диффузии.',
    details: { detector_scores: { ensemble: 0.08, cnn: 0.11 } },
  },
  {
    id: 'screenshot',
    name: 'Скриншот или фото',
    stage: 'artifacts',
    verdict: 'supports_real',
    strength: 0.88,
    reliability: 0.9,
    summary: 'Эвристики интерфейса указывают на фотографию с камеры, а не скриншот.',
    details: {},
  },
  {
    id: 'phash',
    name: 'Оригинальность',
    stage: 'sources',
    verdict: 'supports_real',
    strength: 0.95,
    reliability: 0.92,
    summary: 'Совпадений в архиве нет — материал уникален.',
    details: { similar_in_archive: 0, best_distance: 0.41 },
  },
  {
    id: 'geo',
    name: 'Геолокация',
    stage: 'context',
    verdict: 'supports_real',
    strength: 0.76,
    reliability: 0.85,
    summary: 'GPS в метаданных совпадает с указанным местом съёмки.',
    details: { distance_km: 0.4 },
  },
];

export const DEMO_CHECK: OfferCheck = {
  id: 'chk_demo_01',
  offer_id: 'off_demo_01',
  status: 'done',
  input: {
    type: 'image',
    sha256: 'demo-sha256',
    preview_url: '/demo/preview-01.jpg',
    extracted_text: null,
  },
  trust: DEMO_TRUST,
  signals: DEMO_SIGNALS,
  debate: {
    for_real: [
      { text: 'Метаданные камеры целы и согласуются с геолокацией.', signal_ids: ['exif', 'geo'] },
      { text: 'Следов генерации не найдено.', signal_ids: ['ai_detector'] },
    ],
    for_fake: [{ text: 'Подписи C2PA нет.', signal_ids: ['c2pa'] }],
  },
  provenance: [
    { date: hoursAgo(2), where: 'Люберцы', note: 'Файл загружен автором' },
    { date: hoursAgo(1), where: '—', note: 'Проверка пройдена' },
  ],
  next_steps: [],
  limits: ['Проверка не подтверждает смысл кадра, только подлинность файла.'],
  duration_ms: 4200,
};

export const DEMO_LISTINGS: Listing[] = [
  {
    id: 'lst_demo_01',
    offer_id: 'off_demo_01',
    check_id: 'chk_demo_01',
    title: 'Дым над заводом, Люберцы — фото с места',
    price_rub: 4200,
    currency: 'RUB',
    state: 'available',
    created_at: hoursAgo(1.5),
    expires_at: new Date(now + 6 * 24 * 3600_000).toISOString(),
    trust: DEMO_TRUST,
    facts: {
      origin: 'снято на камеру',
      shot_at: hoursAgo(1.5),
      geo: 'Люберцы, Московская область',
      unique: true,
      similar_in_archive: 0,
    },
    why_price: [
      'Свежесть: снято 1.5 часа назад',
      'Уникальность: нет совпадений в архиве',
      'Метаданные целы, геолокация совпадает с подписью',
      'Категория: городское событие',
    ],
    preview_url: null,
  },
  {
    id: 'lst_demo_02',
    offer_id: 'off_demo_02',
    check_id: 'chk_demo_02',
    title: 'Очередь у пункта выдачи, Тверская',
    price_rub: 1800,
    currency: 'RUB',
    state: 'available',
    created_at: hoursAgo(6),
    expires_at: new Date(now + 5 * 24 * 3600_000).toISOString(),
    trust: { score: 61, uncertainty: 0.31, coverage: 0.7, level: 'likely_real', conflict: false },
    facts: {
      origin: 'снято на камеру',
      shot_at: hoursAgo(6),
      geo: 'Москва, Тверская улица',
      unique: false,
      similar_in_archive: 3,
    },
    why_price: ['Свежесть: снято 6 часов назад', 'Есть похожие кадры в архиве (3)'],
    preview_url: null,
  },
  {
    id: 'lst_demo_03',
    offer_id: 'off_demo_03',
    check_id: 'chk_demo_03',
    title: 'Подтопление перехода после ливня',
    price_rub: 7500,
    currency: 'RUB',
    state: 'sold',
    created_at: hoursAgo(30),
    expires_at: new Date(now + 3 * 24 * 3600_000).toISOString(),
    trust: { score: 90, uncertainty: 0.08, coverage: 0.95, level: 'confirmed', conflict: false },
    facts: {
      origin: 'снято на камеру',
      shot_at: hoursAgo(30),
      geo: 'Казань, ул. Баумана',
      unique: true,
      similar_in_archive: 0,
    },
    why_price: ['Свежесть: снято 30 часов назад', 'ЧП: происшествие', 'Уникальность: нет совпадений'],
    preview_url: null,
  },
];

export const DEMO_STATS: Stats = {
  offers: 12,
  listings: 3,
  sold: 1,
  turnover_rub: 7500,
  commission_rub: 1500,
};

export const DEMO_DEAL: Deal = {
  id: 'deal_demo_01',
  listing_id: 'lst_demo_01',
  buyer: { id: 'org_mash', name: 'Mash' },
  amount_rub: 4200,
  commission_rub: 840,
  author_payout_rub: 3360,
  status: 'paid',
  created_at: new Date().toISOString(),
};

export const DEMO_OFFER: Offer = {
  id: 'off_demo_01',
  status: 'checking',
  created_at: new Date().toISOString(),
  author: { id: 'usr_demo', display_name: 'Аноним', payout: 0 },
  file: { name: 'photo.jpg', size: 1843200, mime: 'image/jpeg', sha256: 'demo', preview_url: null },
  caption: 'Демо-кадр',
  location: 'Люберцы',
  shot_at: hoursAgo(1.5),
};