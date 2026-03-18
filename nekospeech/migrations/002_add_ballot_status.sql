-- Migration 002: Add ballot_status to ie_room for three-state tracking.
-- States: 'no_ballot' (default), 'submitted' (judge submitted, not confirmed),
--         'confirmed' (director confirmed).

DO $$ BEGIN
    CREATE TYPE speech_events.ballot_status AS ENUM ('no_ballot', 'submitted', 'confirmed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE speech_events.ie_room
    ADD COLUMN IF NOT EXISTS ballot_status speech_events.ballot_status NOT NULL DEFAULT 'no_ballot';

-- Backfill existing data: confirmed rooms → 'confirmed', rooms with results → 'submitted'
UPDATE speech_events.ie_room SET ballot_status = 'confirmed' WHERE confirmed = TRUE;

UPDATE speech_events.ie_room r SET ballot_status = 'submitted'
WHERE r.confirmed = FALSE
  AND EXISTS (SELECT 1 FROM speech_events.ie_result res WHERE res.room_id = r.id);
