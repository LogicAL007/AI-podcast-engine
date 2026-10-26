-- Each person's chosen assistant bot (character, name, colours, accessory), shown in the web app.
-- Idempotent, like 0003. Null until they choose; the app then shows the default bot.
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar jsonb;
