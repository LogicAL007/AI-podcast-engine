-- Each person's chosen assistant bot (character, name, colours, accessory), shown in the web app.
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar jsonb;
