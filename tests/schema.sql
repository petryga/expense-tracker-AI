-- Mirror of the BE/ migration that creates the table (BE/ owns the schema).
-- Keep the two the same.
CREATE TABLE category_examples (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid,
  kind text NOT NULL,
  source text NOT NULL,
  text text NOT NULL,
  category text NOT NULL,
  embedding vector(384) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX category_examples_user_kind_source
  ON category_examples (user_id, kind, source) NULLS NOT DISTINCT;
