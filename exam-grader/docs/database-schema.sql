-- database-schema.sql
-- ============================================
-- TEACHERS & AUTH
-- ============================================
CREATE TABLE teachers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) UNIQUE NOT NULL,
  name VARCHAR(255) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  subscription_tier VARCHAR(50) DEFAULT 'free',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- EXAM TEMPLATES (reusable)
-- ============================================
CREATE TABLE exam_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  teacher_id UUID REFERENCES teachers(id) ON DELETE CASCADE,
  
  -- Metadata
  name VARCHAR(255) NOT NULL,
  subject VARCHAR(100) NOT NULL,
  mode VARCHAR(50) NOT NULL, -- 'integrated' | 'separate_answer_sheet'
  max_score DECIMAL(5,2) NOT NULL,
  
  -- Template files
  template_image_url TEXT, -- for integrated mode
  question_book_url TEXT, -- for separate mode (PDF)
  answer_sheet_template_url TEXT, -- for separate mode
  
  -- Extracted structure
  structure_json JSONB NOT NULL,
  -- Example structure:
  -- {
  --   "sections": [
  --     {
  --       "name": "LISTENING",
  --       "total_points": 25,
  --       "parts": [
  --         {
  --           "name": "Multiple Choice",
  --           "questions": ["1","2","3","4","5"],
  --           "type": "multiple_choice",
  --           "options": ["A","B","C"],
  --           "points_each": 2.5
  --         }
  --       ]
  --     }
  --   ]
  -- }
  
  -- Answer key
  answer_key_json JSONB NOT NULL,
  -- Example:
  -- {
  --   "1": "B",
  --   "2": "A",
  --   "3": "photosynthesis is the process...",
  --   ...
  -- }
  
  answer_key_method VARCHAR(50), -- 'manual' | 'auto_extract' | 'excel'
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- GRADING SESSIONS (batch processing)
-- ============================================
CREATE TABLE grading_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id UUID REFERENCES exam_templates(id) ON DELETE CASCADE,
  teacher_id UUID REFERENCES teachers(id) ON DELETE CASCADE,
  
  name VARCHAR(255) NOT NULL, -- "Group A - March 2026"
  total_students INTEGER DEFAULT 0,
  processed_students INTEGER DEFAULT 0,
  status VARCHAR(50) DEFAULT 'processing', -- 'processing' | 'completed' | 'failed'
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- STUDENT EXAMS (individual)
-- ============================================
CREATE TABLE student_exams (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID REFERENCES grading_sessions(id) ON DELETE CASCADE,
  
  student_name VARCHAR(255),
  student_id VARCHAR(100), -- if extracted from exam
  
  -- Images
  image_urls TEXT[], -- array of photo URLs (multi-page support)
  page_count INTEGER DEFAULT 1,
  
  -- Extracted data
  extracted_answers_json JSONB,
  -- Example:
  -- {
  --   "1": "B",
  --   "2": "C",
  --   "3": "Plants use sunlight to make energy",
  --   ...
  -- }
  
  -- Processing status
  status VARCHAR(50) DEFAULT 'pending', -- 'pending' | 'processing' | 'graded' | 'review_needed' | 'error'
  error_message TEXT,
  needs_review_reason TEXT, -- e.g., "Name not detected clearly"
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- GRADING RESULTS
-- ============================================
CREATE TABLE grading_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  exam_id UUID REFERENCES student_exams(id) ON DELETE CASCADE,
  
  -- Scores
  total_score DECIMAL(5,2) NOT NULL,
  max_score DECIMAL(5,2) NOT NULL,
  percentage DECIMAL(5,2) GENERATED ALWAYS AS ((total_score / max_score) * 100) STORED,
  
  -- Detailed breakdown
  section_scores_json JSONB,
  -- Example:
  -- {
  --   "LISTENING": {
  --     "earned": 20,
  --     "max": 25,
  --     "details": {
  --       "Part 1 - Multiple Choice": {"earned": 10, "max": 12.5},
  --       "Part 2 - Complete Sentence": {"earned": 10, "max": 12.5}
  --     }
  --   },
  --   "WRITING & GRAMMAR": {...}
  -- }
  
  -- AI Feedback
  feedback_json JSONB,
  -- Example:
  -- {
  --   "overall": "Good understanding of basic concepts...",
  --   "strengths": ["Strong in multiple choice", "Clear handwriting"],
  --   "improvements": ["Review verb conjugation", "Practice spelling"],
  --   "question_feedback": {
  --     "3": "Correct concept but missing example",
  --     "7": "Incorrect tense usage"
  --   }
  -- }
  
  -- Teacher corrections
  teacher_corrections_json JSONB,
  -- Example:
  -- {
  --   "5": {"original_score": 0, "corrected_score": 2.5, "reason": "Answer was correct"}
  -- }
  
  final_score DECIMAL(5,2), -- after teacher corrections
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- INDEXES
-- ============================================
CREATE INDEX idx_templates_teacher ON exam_templates(teacher_id);
CREATE INDEX idx_sessions_teacher ON grading_sessions(teacher_id);
CREATE INDEX idx_sessions_template ON grading_sessions(template_id);
CREATE INDEX idx_exams_session ON student_exams(session_id);
CREATE INDEX idx_exams_status ON student_exams(status);
CREATE INDEX idx_results_exam ON grading_results(exam_id);
