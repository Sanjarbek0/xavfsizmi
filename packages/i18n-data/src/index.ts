import en from './en/common.json' with { type: 'json' };
import ru from './ru/common.json' with { type: 'json' };
import uz from './uz/common.json' with { type: 'json' };

export { en, ru, uz };
export type Translations = typeof en;
