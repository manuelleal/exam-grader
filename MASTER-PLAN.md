# EXAM GRADER - MASTER PLAN
**AI-Powered Exam Grading System**
Version: MVP 1.0 | Date: March 2026

---

## 1. EXECUTIVE SUMMARY

### Product Vision
SaaS platform for teachers to automatically grade exams using AI vision and grading capabilities.

### MVP Scope
- English exams (expand to other subjects later)
- Support multiple exam formats (integrated sheets, separate answer sheets)
- Batch processing: 35 exams per session
- Multi-page exams (1-4 photos per student)
- Web app first, mobile-ready architecture

### Key Constraints
- Teacher uploads photos in sequence (student order maintained)
- Name detection: usually first page, sometimes all pages
- Out of order uploads: deferred to future version
- Budget: Minimize API costs while maintaining quality

---

## 2. SYSTEM ARCHITECTURE

### High-Level Flow
```
┌─────────────────────────────────────────────────────────────┐
│                      TEACHER INTERFACE                      │
│  Upload Exam Template → Upload Student Photos → Review      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    API GATEWAY (FastAPI)                    │
│              /auth  /templates  /grading  /results          │
└─────────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
┌───────────────┐   ┌──────────────┐   ┌──────────────┐
│ VISION ENGINE │   │GRADING ENGINE│   │   DATABASE   │
│  PaddleOCR    │   │ Claude API   │   │  Supabase    │
│  + Claude     │   │ GPT-4o-mini  │   │  Postgres    │
└───────────────┘   └──────────────┘   └──────────────┘
        ↓                   ↓                   ↓
┌─────────────────────────────────────────────────────────────┐
│                    STORAGE LAYER                            │
│         Cloudinary (images) + Supabase (metadata)           │
└─────────────────────────────────────────────────────────────┘
```

### Processing Pipeline

**Stage 1: Template Setup**
```
Teacher uploads exam template (clean copy)
    ↓
PaddleOCR extracts text structure
    ↓
Claude Haiku structures to JSON schema
    ↓
Teacher configures answer key (3 methods):
    - Manual entry UI
    - Auto-extract from book
    - Upload Excel
    ↓
Template saved to DB
```

**Stage 2: Student Exam Processing**
```
Teacher uploads photos (batch, sequential)
    ↓
Name detection (first page of each student)
    ↓
Group photos by student:
    - Has name → new student
    - No name → continuation of previous
    ↓
PaddleOCR per page
    ↓
Merge pages → consolidated JSON per student
    ↓
Claude validates + structures answers
    ↓
Grading engine compares vs answer key
    ↓
Results stored + teacher review
```

---

## 3. DATABASE SCHEMA (Supabase Postgres)

```sql
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
```

---

## 4. TECH STACK

### Backend
```yaml
Language: Python 3.11+
Framework: FastAPI
  - async support
  - auto OpenAPI docs
  - fast development

Key Libraries:
  - paddleocr: OCR engine (free, accurate)
  - anthropic: Claude API client
  - openai: GPT-4o-mini for grading
  - supabase: Database client
  - cloudinary: Image storage
  - python-jose: JWT auth
  - passlib: Password hashing
  - pydantic: Data validation
  - python-multipart: File uploads
  - celery: Background tasks (future)
```

### Frontend
```yaml
Framework: React 18 + Vite
UI Library: TailwindCSS + shadcn/ui
State: Zustand (lightweight)
Forms: React Hook Form + Zod
File Upload: react-dropzone
API Client: Axios
Camera: react-webcam (future mobile)
PWA: Vite PWA plugin
```

### Infrastructure
```yaml
Database: Supabase (Postgres)
Storage: Cloudinary (25GB free tier)
Auth: JWT + Supabase Auth (optional)
Deployment: 
  - Backend: Railway / Render
  - Frontend: Vercel / Netlify
Environment: Docker Compose (local dev)
```

### AI Services
```yaml
OCR: PaddleOCR (local, free)
Vision: Claude 3.5 Sonnet (structure validation)
Grading: GPT-4o-mini (cost-effective)
Fallback: Gemini Flash (free tier)

Cost per session (35 exams):
  - OCR: $0
  - Claude: ~$0.10
  - GPT-4o-mini: ~$0.05
  Total: ~$0.15/session
```

---

## 5. API ENDPOINTS

### Authentication
```
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
GET    /api/v1/auth/me
```

### Exam Templates
```
POST   /api/v1/templates                    # Create new template
GET    /api/v1/templates                    # List templates
GET    /api/v1/templates/{id}               # Get template details
PUT    /api/v1/templates/{id}               # Update template
DELETE /api/v1/templates/{id}               # Delete template

POST   /api/v1/templates/{id}/extract       # Extract structure from upload
POST   /api/v1/templates/{id}/answer-key    # Set answer key
```

### Grading Sessions
```
POST   /api/v1/sessions                     # Create grading session
GET    /api/v1/sessions                     # List sessions
GET    /api/v1/sessions/{id}                # Get session details
POST   /api/v1/sessions/{id}/upload         # Upload student photos (batch)
POST   /api/v1/sessions/{id}/process        # Trigger processing
GET    /api/v1/sessions/{id}/status         # Check processing status
```

### Student Exams
```
GET    /api/v1/sessions/{id}/exams          # List exams in session
GET    /api/v1/exams/{id}                   # Get exam details
PUT    /api/v1/exams/{id}/review            # Teacher review/corrections
DELETE /api/v1/exams/{id}                   # Delete exam
```

### Results
```
GET    /api/v1/exams/{id}/result            # Get grading result
PUT    /api/v1/results/{id}/correct         # Apply teacher corrections
GET    /api/v1/sessions/{id}/export         # Export grades (CSV/Excel)
GET    /api/v1/sessions/{id}/analytics      # Session statistics
```

---

## 6. PROJECT STRUCTURE

```
exam-grader/
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app entry
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── auth.py           # Auth endpoints
│   │   │       ├── templates.py      # Template management
│   │   │       ├── sessions.py       # Grading sessions
│   │   │       ├── exams.py          # Student exams
│   │   │       └── results.py        # Results & export
│   │   │
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py             # Settings (env vars)
│   │   │   ├── security.py           # JWT, password hashing
│   │   │   └── database.py           # Supabase connection
│   │   │
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── teacher.py            # Teacher model
│   │   │   ├── template.py           # Template model
│   │   │   ├── session.py            # Session model
│   │   │   ├── exam.py               # Exam model
│   │   │   └── result.py             # Result model
│   │   │
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py               # Auth DTOs
│   │   │   ├── template.py           # Template DTOs
│   │   │   ├── session.py            # Session DTOs
│   │   │   ├── exam.py               # Exam DTOs
│   │   │   └── result.py             # Result DTOs
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── ocr_service.py        # PaddleOCR wrapper
│   │   │   ├── vision_service.py     # Claude vision calls
│   │   │   ├── grading_service.py    # Grading logic
│   │   │   ├── storage_service.py    # Cloudinary wrapper
│   │   │   ├── grouping_service.py   # Multi-page grouping
│   │   │   └── export_service.py     # CSV/Excel export
│   │   │
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── image_processing.py   # Image preprocessing
│   │       └── validators.py         # Custom validators
│   │
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_auth.py
│   │   ├── test_templates.py
│   │   └── test_grading.py
│   │
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/
│   ├── public/
│   │   └── manifest.json            # PWA manifest
│   │
│   ├── src/
│   │   ├── components/
│   │   │   ├── auth/
│   │   │   │   ├── LoginForm.jsx
│   │   │   │   └── RegisterForm.jsx
│   │   │   │
│   │   │   ├── templates/
│   │   │   │   ├── TemplateList.jsx
│   │   │   │   ├── TemplateCreator.jsx
│   │   │   │   └── AnswerKeyEditor.jsx
│   │   │   │
│   │   │   ├── sessions/
│   │   │   │   ├── SessionList.jsx
│   │   │   │   ├── PhotoUploader.jsx
│   │   │   │   └── ProcessingStatus.jsx
│   │   │   │
│   │   │   ├── results/
│   │   │   │   ├── ExamReview.jsx
│   │   │   │   ├── ScoreCard.jsx
│   │   │   │   └── FeedbackDisplay.jsx
│   │   │   │
│   │   │   └── ui/                  # shadcn components
│   │   │       ├── button.jsx
│   │   │       ├── card.jsx
│   │   │       ├── dialog.jsx
│   │   │       └── ...
│   │   │
│   │   ├── pages/
│   │   │   ├── Login.jsx
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Templates.jsx
│   │   │   ├── Sessions.jsx
│   │   │   └── Results.jsx
│   │   │
│   │   ├── services/
│   │   │   ├── api.js               # Axios instance
│   │   │   ├── auth.js              # Auth API calls
│   │   │   ├── templates.js         # Template API calls
│   │   │   └── sessions.js          # Session API calls
│   │   │
│   │   ├── store/
│   │   │   ├── authStore.js         # Auth state
│   │   │   └── appStore.js          # App state
│   │   │
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   │
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── .env.example
│
├── docs/
│   ├── MASTER-PLAN.md              # This file
│   ├── API.md                      # API documentation
│   └── DEPLOYMENT.md               # Deployment guide
│
├── docker-compose.yml
└── README.md
```

---

## 7. WINDSURF EXECUTION TASKS

### Phase 1: Project Setup (Day 1 - Morning)

**Task 1.1: Initialize Backend**
```bash
# Create project structure
mkdir -p exam-grader/backend/app/{api/v1,core,models,schemas,services,utils}
cd exam-grader/backend

# Create requirements.txt
# Create .env.example
# Initialize FastAPI app in main.py
# Setup database connection in core/database.py
# Configure settings in core/config.py
```

**Task 1.2: Initialize Frontend**
```bash
cd ../
npm create vite@latest frontend -- --template react
cd frontend
npm install
# Install dependencies: tailwindcss, shadcn, axios, zustand, react-router-dom
# Setup Tailwind config
# Create basic routing structure
```

**Task 1.3: Database Setup**
```sql
# Connect to Supabase
# Run schema.sql to create all tables
# Create row-level security policies
# Test connection from backend
```

---

### Phase 2: Core Services (Day 1 - Afternoon)

**Task 2.1: OCR Service**
```python
# File: backend/app/services/ocr_service.py
# Implement PaddleOCR wrapper
# Function: extract_text_from_image(image_path) -> str
# Function: detect_text_regions(image_path) -> List[Region]
# Handle image preprocessing (rotation, contrast)
```

**Task 2.2: Vision Service**
```python
# File: backend/app/services/vision_service.py
# Implement Claude API integration
# Function: structure_exam_template(ocr_text) -> ExamStructure
# Function: validate_student_answers(ocr_text, template) -> AnswersDict
# Error handling and retries
```

**Task 2.3: Grouping Service**
```python
# File: backend/app/services/grouping_service.py
# Implement multi-page grouping logic
# Function: group_photos_by_student(photo_list) -> Dict[student, photos]
# Logic: Name detection on first page, continuation on subsequent
```

---

### Phase 3: API Endpoints (Day 2 - Morning)

**Task 3.1: Auth Endpoints**
```python
# File: backend/app/api/v1/auth.py
# POST /register - create teacher account
# POST /login - return JWT token
# GET /me - get current user
# Implement JWT middleware
```

**Task 3.2: Template Endpoints**
```python
# File: backend/app/api/v1/templates.py
# POST /templates - create template
# POST /templates/{id}/extract - process uploaded template
# POST /templates/{id}/answer-key - set answer key (3 methods)
# GET /templates - list teacher's templates
```

**Task 3.3: Session Endpoints**
```python
# File: backend/app/api/v1/sessions.py
# POST /sessions - create grading session
# POST /sessions/{id}/upload - batch photo upload
# POST /sessions/{id}/process - trigger async processing
# GET /sessions/{id}/status - polling endpoint
```

---

### Phase 4: Grading Engine (Day 2 - Afternoon)

**Task 4.1: Grading Service**
```python
# File: backend/app/services/grading_service.py
# Function: grade_multiple_choice(student_ans, correct_ans) -> score
# Function: grade_short_answer(student_ans, correct_ans, use_ai=True) -> score
# Function: generate_feedback(exam_results) -> feedback_dict
# Integrate GPT-4o-mini for semantic comparison
```

**Task 4.2: Export Service**
```python
# File: backend/app/services/export_service.py
# Function: export_to_csv(session_id) -> csv_file
# Function: export_to_excel(session_id) -> xlsx_file
# Include: names, scores, section breakdown
```

---

### Phase 5: Frontend UI (Day 3)

**Task 5.1: Authentication Pages**
```jsx
// Login.jsx - login form
// Register.jsx - registration
// AuthProvider - context wrapper
// Protected routes setup
```

**Task 5.2: Template Management**
```jsx
// TemplateCreator.jsx - upload template wizard
// AnswerKeyEditor.jsx - 3 input methods (manual/auto/excel)
// TemplateList.jsx - view saved templates
```

**Task 5.3: Grading Workflow**
```jsx
// PhotoUploader.jsx - drag-drop batch upload
// ProcessingStatus.jsx - real-time progress
// ExamReview.jsx - review extracted answers
// ScoreCard.jsx - display results
```

**Task 5.4: Results Dashboard**
```jsx
// SessionResults.jsx - list all graded exams
// Analytics.jsx - class statistics
// ExportButton.jsx - download CSV/Excel
```

---

### Phase 6: Integration & Testing (Day 4)

**Task 6.1: End-to-End Flow**
```
Test complete workflow:
1. Register teacher
2. Create template
3. Upload student photos
4. Process batch
5. Review results
6. Export grades
```

**Task 6.2: Error Handling**
```
- Image upload failures
- OCR errors (blurry image)
- Name detection failures
- API rate limits
- Storage limits
```

**Task 6.3: Edge Cases**
```
- Multiple students same name
- Photos out of order (deferred)
- Missing pages
- Handwriting too messy
- Answer key mistakes
```

---

## 8. ENVIRONMENT VARIABLES

### Backend (.env)
```bash
# Database
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJxxxx...
DATABASE_URL=postgresql://postgres:password@db.xxxxx.supabase.co:5432/postgres

# AI Services
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx

# Storage
CLOUDINARY_CLOUD_NAME=xxxxx
CLOUDINARY_API_KEY=xxxxx
CLOUDINARY_API_SECRET=xxxxx

# Auth
JWT_SECRET=your-super-secret-key-change-this
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# App
ENVIRONMENT=development
DEBUG=True
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

### Frontend (.env)
```bash
VITE_API_URL=http://localhost:8000/api/v1
VITE_APP_NAME=ExamGrader
```

---

## 9. DEPLOYMENT STRATEGY

### MVP Deployment (Free Tier)
```yaml
Backend:
  Platform: Railway (free tier)
  - Auto-deploy from GitHub
  - Environment variables via UI
  - PostgreSQL addon available

Frontend:
  Platform: Vercel
  - Auto-deploy from GitHub
  - Environment variables via UI
  - Free SSL + CDN

Database:
  Supabase (free tier)
  - 500MB database
  - 1GB file storage
  - Row-level security

Storage:
  Cloudinary (free tier)
  - 25GB storage
  - 25GB bandwidth/month
```

### Production Scaling (Future)
```yaml
Backend:
  - Railway Pro / AWS ECS
  - Redis for caching
  - Celery for async tasks
  - Load balancing

Frontend:
  - Vercel Pro
  - CDN optimization
  - PWA installable

Database:
  - Supabase Pro
  - Read replicas
  - Automatic backups

Monitoring:
  - Sentry (errors)
  - PostHog (analytics)
  - LogRocket (sessions)
```

---

## 10. COST ANALYSIS

### MVP Operating Costs (per month)

**AI APIs (35 exams/session, 10 sessions/month)**
```
OCR: $0 (PaddleOCR local)
Claude API: 350 exams × $0.003 = $1.05
GPT-4o-mini: 350 exams × $0.0015 = $0.53
Total AI: ~$1.60/month
```

**Infrastructure**
```
Supabase: $0 (free tier, <500MB)
Cloudinary: $0 (free tier, <25GB)
Railway: $0 (free tier) OR $5/month (hobby)
Vercel: $0 (free tier)
Total Infrastructure: $0-5/month
```

**Total MVP Cost: $2-7/month**

### Revenue Projection (SaaS model)
```
Pricing tiers:
- Free: 5 exams/month
- Basic: $9/month (50 exams)
- Pro: $29/month (200 exams)
- School: $99/month (unlimited)

Break-even: 1 Basic subscriber
Profitability: 3+ subscribers
```

---

## 11. CRITICAL SUCCESS FACTORS

### Technical
- [ ] OCR accuracy >85% for handwriting
- [ ] Multi-page grouping accuracy >95%
- [ ] Processing time <30 seconds per exam
- [ ] Zero data loss on uploads
- [ ] Mobile-responsive UI

### User Experience
- [ ] Template creation <5 minutes
- [ ] Batch upload <2 minutes for 35 exams
- [ ] Results available <10 minutes after upload
- [ ] Intuitive review interface
- [ ] Export in common formats (CSV, Excel)

### Business
- [ ] MVP launched within 4 days
- [ ] First paying customer within 2 weeks
- [ ] Net Promoter Score >8/10
- [ ] Churn rate <10%
- [ ] Expand to 3+ subjects in 3 months

---

## 12. RISK MITIGATION

### Technical Risks

**Risk: OCR fails on poor handwriting**
- Mitigation: Manual review interface for low-confidence results
- Backup: Teacher can override any answer

**Risk: Name detection fails (grouping errors)**
- Mitigation: Preview grouped exams before processing
- Backup: Manual reordering interface (future)

**Risk: API rate limits exceeded**
- Mitigation: Queue system with rate limiting
- Backup: Batch processing overnight

**Risk: Storage limits exceeded**
- Mitigation: Auto-compress images after processing
- Backup: Delete processed images after 30 days

### Business Risks

**Risk: Teachers don't adopt**
- Mitigation: Free tier with generous limits
- Validation: Beta test with 5 teachers

**Risk: AI grading not trusted**
- Mitigation: Always show teacher review interface
- Strategy: Position as "assistant" not "replacement"

**Risk: Competitors launch first**
- Mitigation: Speed to market (MVP in 4 days)
- Differentiation: Multi-format support, mobile-first

---

## 13. FUTURE ROADMAP

### Version 1.1 (1 month)
- Mobile app (Capacitor)
- Photo reordering interface
- Multiple exam templates per subject
- Performance analytics dashboard

### Version 1.2 (2 months)
- Math equation recognition
- Essay grading with rubrics
- Plagiarism detection
- Student progress tracking

### Version 2.0 (3 months)
- Multi-language support (Spanish, French)
- LMS integrations (Google Classroom, Canvas)
- Parent portal
- AI tutoring recommendations

### Enterprise Features (6 months)
- School district deployment
- Advanced analytics
- API for third-party integrations
- White-label option

---

## 14. WINDSURF PROMPT TEMPLATES

### For Backend Development
```
Create FastAPI endpoint for [FEATURE] with:
- Async route handler
- Pydantic schema validation
- Supabase database operations
- Error handling with proper HTTP codes
- JWT authentication middleware
- OpenAPI documentation

Follow project structure in /backend/app/
Use existing services from /services/
```

### For Frontend Development
```
Create React component for [FEATURE] with:
- TailwindCSS styling
- shadcn/ui components
- Form validation with react-hook-form + zod
- API calls via axios
- Loading states
- Error handling
- Responsive design (mobile-first)

Follow component structure in /frontend/src/components/
Use existing API service from /services/
```

### For Service Layer
```
Create service class for [FEATURE] with:
- Type hints for all functions
- Error handling with custom exceptions
- Logging for debugging
- Retry logic for external APIs
- Unit tests

Follow service pattern in /services/
Use config from core/config.py
```

---

## 15. VALIDATION CHECKLIST

### Before MVP Launch
- [ ] Can create teacher account
- [ ] Can upload exam template
- [ ] Can set answer key (all 3 methods work)
- [ ] Can upload batch of student photos
- [ ] Multi-page grouping works correctly
- [ ] OCR extracts text accurately
- [ ] Grading produces correct scores
- [ ] Feedback is relevant and helpful
- [ ] Teacher can review and correct results
- [ ] Can export grades to CSV/Excel
- [ ] Mobile-responsive on all pages
- [ ] Error messages are user-friendly
- [ ] Loading states show progress
- [ ] No data loss on any operation

### Performance Benchmarks
- [ ] Template extraction: <30 seconds
- [ ] Single exam processing: <20 seconds
- [ ] Batch of 35 exams: <15 minutes
- [ ] Page load time: <2 seconds
- [ ] API response time: <500ms (p95)

---

## 16. SUPPORT & DOCUMENTATION

### User Documentation (to create)
- Getting Started Guide
- Template Creation Tutorial
- Grading Workflow Guide
- Troubleshooting Common Issues
- FAQ

### Developer Documentation (to create)
- API Reference
- Database Schema Reference
- Service Layer Documentation
- Deployment Guide
- Contributing Guidelines

---

## END OF MASTER PLAN

**Next Steps:**
1. Review this document
2. Set up development environment
3. Execute Windsurf tasks in order
4. Deploy MVP in 4 days
5. Launch beta with first teachers

**Questions before starting? Review sections 7-14 for implementation details.**

---

*Document Version: 1.0*
*Last Updated: March 15, 2026*
*Author: AI Architecture Team*
