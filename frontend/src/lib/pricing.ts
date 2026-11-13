import type { Offer, OfferCheck, SignalResult } from '../types';

/**
 * Предварительная оценка по правилу из docs/CONTRACT.md:
 * price = base × freshness × uniqueness × provenance × demand, округление до 100.
 * Это не «AI решил»: каждый множитель объясняется строкой why_price.
 * Итоговую цену подтверждает backend на карточке лота.
 */

const BASE = 1500;

export interface Estimate {
  priceRub: number;
  whyPrice: string[];
  /** Дубликат в архиве — лот не выставляется. */
  blocked: boolean;
}

function plural(count: number, forms: [string, string, string]): string {
  const abs = Math.abs(count) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}

function hoursSince(iso: string | null): number | null {
  if (!iso) return null;
  const time = Date.parse(iso);
  if (Number.isNaN(time)) return null;
  return Math.max(0, (Date.now() - time) / 3_600_000);
}

function freshnessFactor(hours: number | null): { factor: number; text: string } {
  if (hours === null) return { factor: 1, text: 'Свежесть: время съёмки неизвестно, множитель ×1.0' };
  const shown = hours < 1 ? `${Math.max(1, Math.round(hours * 60))} мин` : `${hours.toFixed(1)} ч`;
  if (hours < 1) return { factor: 3, text: `Свежесть: снято ${shown} назад, множитель ×3.0` };
  if (hours < 6) return { factor: 2, text: `Свежесть: снято ${hours.toFixed(1)} ч назад, множитель ×2.0` };
  if (hours < 24) return { factor: 1.5, text: `Свежесть: снято ${hours.toFixed(1)} ч назад, множитель ×1.5` };
  if (hours < 72) return { factor: 1, text: `Свежесть: снято ${Math.round(hours)} ч назад, множитель ×1.0` };
  return { factor: 0.5, text: `Свежесть: снято ${Math.round(hours / 24)} ${plural(Math.round(hours / 24), ['день', 'дня', 'дней'])} назад, множитель ×0.5` };
}

function uniquenessFactor(signals: SignalResult[]): {
  factor: number;
  text: string;
  blocked: boolean;
} {
  const archive = signals.find((signal) => signal.id === 'phash' || signal.name.toLowerCase().includes('оригиналь'));
  if (!archive) {
    return { factor: 1, text: 'Уникальность: сигнал проверки архива недоступен, множитель ×1.0', blocked: false };
  }
  const similar = archive.details.similar_in_archive;
  const count = typeof similar === 'number' && Number.isFinite(similar) ? Math.round(similar) : null;

  if (archive.verdict === 'supports_fake') {
    return { factor: 0, text: 'Уникальность: найден дубликат в архиве, лот не выставляется', blocked: true };
  }
  if (count !== null && count > 0) {
    return {
      factor: 1,
      text: `Уникальность: похожих кадров в архиве — ${count}, множитель ×1.0`,
      blocked: false,
    };
  }
  return {
    factor: 2,
    text: count === 0
      ? 'Уникальность: совпадений в архиве нет, множитель ×2.0'
      : 'Уникальность: совпадений не найдено, множитель ×2.0',
    blocked: false,
  };
}

function provenanceFactor(signals: SignalResult[]): { factor: number; text: string } {
  const provenance = signals.filter((signal) => signal.stage === 'provenance');
  if (provenance.length === 0) {
    return { factor: 0.7, text: 'Происхождение: метаданных нет, множитель ×0.7' };
  }
  const strong = provenance.filter(
    (signal) => signal.verdict === 'supports_real' && signal.reliability >= 0.6,
  ).length;
  if (strong >= 2) {
    return { factor: 1.5, text: 'Происхождение: метаданные целы и геолокация совпадает, множитель ×1.5' };
  }
  if (strong === 1) {
    return { factor: 1, text: 'Происхождение: метаданные частичные, множитель ×1.0' };
  }
  return { factor: 0.7, text: 'Происхождение: метаданные не подтверждают источник, множитель ×0.7' };
}

/** Детерминированная предварительная цена по проверке и данным заявки. */
export function estimatePrice(offer: Offer, check: OfferCheck): Estimate {
  const hours = hoursSince(offer.shot_at);
  const fresh = freshnessFactor(hours);
  const unique = uniquenessFactor(check.signals);
  const provenance = provenanceFactor(check.signals);

  if (unique.blocked) {
    return { priceRub: 0, whyPrice: [fresh.text, unique.text, provenance.text], blocked: true };
  }

  const raw = BASE * fresh.factor * unique.factor * provenance.factor;
  const priceRub = Math.round(raw / 100) * 100;

  return {
    priceRub,
    blocked: false,
    whyPrice: [
      `Базовая ставка: ${BASE} ₽`,
      fresh.text,
      unique.text,
      provenance.text,
      'Категория события не определена: множитель спроса ×1.0',
    ],
  };
}