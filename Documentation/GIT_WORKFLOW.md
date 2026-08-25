# Git Workflow Guide

## Getting Started

```bash
# Clone the repository
git clone https://github.com/vinayj6/CommunicationIQ.git
cd CommunicationIQ

# Create a feature branch
git checkout -b feature/your-feature-name

# Install dependencies
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm install

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env with your MONGO_URI and JWT_SECRET
```

## Branch Strategy

- **main** — production-ready code, always deployable
- **feature/** — new features (e.g., `feature/batch-import`)
- **fix/** — bug fixes (e.g., `fix/score-calculation`)
- **docs/** — documentation changes

## Development Workflow

1. **Pull latest**: `git pull origin main`
2. **Create branch**: `git checkout -b feature/my-feature`
3. **Make changes**: edit files, run tests
4. **Test**: `cd backend && .venv/Scripts/python -m pytest` and `cd frontend && npx vitest run`
5. **Commit**: `git add . && git commit -m "feat: add batch user import"`
6. **Push**: `git push origin feature/my-feature`
7. **Create Pull Request** on GitHub
8. **Review and merge** into main

## Commit Message Convention

```
feat: add batch user import
fix: correct score calculation for fluency
docs: update API documentation
refactor: simplify tenant isolation logic
test: add coverage for invite flow
```

## Rules

- **Never commit** `.env`, `.env.local`, or any file with secrets
- **Never commit** `node_modules/`, `.venv/`, `__pycache__/`, `.next/`
- **Always pull** before starting work to avoid merge conflicts
- **Keep commits focused** — one logical change per commit
- **Run tests** before pushing to main
- **Update documentation** when behavior changes
- **Do not directly modify main** unless you are a maintainer
- **Resolve conflicts** locally before pushing

## MongoDB

- The shared MongoDB Atlas cluster is used for development
- All developers connect to the same database via `MONGO_URI`
- **Never delete** another developer's test data without coordinating
- **Never modify** production tenant data directly
- Use `python -m app.seed --reset` to restore a clean state locally

## Environment Variables

```bash
# Required for backend
MONGO_URI=mongodb://...    # MongoDB Atlas connection string
JWT_SECRET=...             # JWT signing secret
APP_URL=http://localhost:3010
```

Never commit these values. Use `.env.example` as a template.

## Testing

```bash
# Backend
cd backend
.venv/Scripts/python -m pytest -v

# Frontend
cd frontend
npx vitest run

# Frontend build check
cd frontend
npx next build
```
