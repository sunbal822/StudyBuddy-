-- ====================================================================
-- StudyBuddy AI - Supabase Database Schema
-- Run this in your Supabase SQL Editor: Dashboard > SQL Editor > New Query
-- ====================================================================

-- 1. Create quiz_history table
create table if not exists public.quiz_history (
    id bigint generated always as identity primary key,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null,
    topic text not null,
    difficulty text not null default 'Medium',
    score integer not null,
    total_questions integer not null default 5,
    weak_concepts text[] default array[]::text[]
);

-- 2. Create index for fast chronological sorting
create index if not exists idx_quiz_history_created_at 
on public.quiz_history (created_at desc);

-- 3. Enable Row Level Security (RLS)
alter table public.quiz_history enable row level security;

-- 4. RLS Policies: Allow public anonymous demo access
create policy "Allow anonymous insert on quiz_history"
on public.quiz_history
for insert
to anon
with check (true);

create policy "Allow anonymous read on quiz_history"
on public.quiz_history
for select
to anon
using (true);
