-- Migration 003: Add nickname column to ie_room.
-- Allows tournament directors to assign human-friendly names to rooms
-- (e.g., "Room 101", "Auditorium A") instead of generic "Room 1", "Room 2".

ALTER TABLE speech_events.ie_room
    ADD COLUMN IF NOT EXISTS nickname VARCHAR(100) DEFAULT NULL;
