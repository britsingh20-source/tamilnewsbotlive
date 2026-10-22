import { sqliteTable, text } from 'drizzle-orm/sqlite-core';
export const records = sqliteTable('crm_records', { id: text('id').primaryKey(), owner: text('owner').notNull(), data: text('data').notNull(), updated: text('updated').notNull() });
