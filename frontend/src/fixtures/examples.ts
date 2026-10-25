export type ExampleId = 'supported' | 'context' | 'insufficient';

export interface Example {
  id: ExampleId;
  title: string;
  hint: string;
  text: string;
}

/**
 * Учебные примеры. Все организации и события вымышлены,
 * примеры нужны только для демонстрации сценария.
 */
export const EXAMPLES: readonly Example[] = [
  {
    id: 'supported',
    title: 'Подтверждаемое сообщение',
    hint: 'Есть объявление организации и дата вступления в силу',
    text: 'Библиотека «Октябрь» на Выборгской улице переходит на круглосуточный режим с 1 ноября. Об этом сообщили в пресс-службе библиотеки.',
  },
  {
    id: 'context',
    title: 'Пропущено условие',
    hint: 'Правило действует не для всех и не всегда',
    text: 'Городская парковка стала бесплатной по выходным. Владельцы машин больше не платят за стоянку в центре города.',
  },
  {
    id: 'insufficient',
    title: 'Недостаточно данных',
    hint: 'Источников нет — утверждение нельзя ни подтвердить, ни опровергнуть',
    text: 'С января в городе отменят бумажные квитанции за электричество: «Северный ток» полностью перейдёт на электронные счета.',
  },
];

export function findExampleByText(text: string): Example | undefined {
  const normalized = text.trim().replace(/\s+/g, ' ');
  return EXAMPLES.find((example) => example.text.replace(/\s+/g, ' ') === normalized);
}
