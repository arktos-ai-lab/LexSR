# Contributing to LexSR

Thank you for your interest in contributing to the Suriname Legal Knowledge Fabric! This document provides guidelines for contributing to the project.

---

## Code of Conduct

This project adheres to principles of transparency, collaboration, and respect. We welcome contributions from developers, legal experts, researchers, and anyone passionate about access to justice.

---

## How Can I Contribute?

### 1. Reporting Bugs

If you find a bug, please create an issue with:
- **Clear title**: "Citation resolver fails on EU directive references"
- **Description**: What you expected vs. what happened
- **Reproduction steps**: Minimal code to reproduce the issue
- **Environment**: Python version, OS, relevant dependencies

### 2. Suggesting Features

Feature requests are welcome! Please:
- Check existing issues to avoid duplicates
- Describe the use case and benefit
- Propose an implementation approach (optional)
- Tag with `enhancement` label

### 3. Improving Documentation

Documentation improvements are always appreciated:
- Fix typos, clarify confusing sections
- Add examples and tutorials
- Translate documentation (future: English, Spanish)
- Document edge cases and gotchas

### 4. Writing Code

Code contributions should follow the development workflow below.

---

## Development Workflow

### Step 1: Fork and Clone

```bash
# Fork the repository on GitHub
# Then clone your fork
git clone https://github.com/YOUR_USERNAME/wetten-van-suriname.git
cd wetten-van-suriname
```

### Step 2: Create a Branch

```bash
# Create a feature branch
git checkout -b feature/your-feature-name

# Or a bugfix branch
git checkout -b fix/issue-123
```

### Step 3: Set Up Development Environment

```bash
# Install in development mode with all extras
pip install -e ".[dev,all]"

# Run tests to ensure everything works
pytest tests/ -v
```

### Step 4: Make Your Changes

- Write clean, readable code
- Follow the code style (see below)
- Add tests for new functionality
- Update documentation as needed

### Step 5: Run Tests and Linting

```bash
# Run all tests
pytest tests/ -v

# Check code coverage (target: >80%)
pytest tests/ --cov=src/lexsr --cov-report=html

# Run linting
ruff check src/ tests/

# Auto-fix linting issues
ruff check src/ tests/ --fix

# Run type checking (optional but recommended)
mypy src/lexsr
```

### Step 6: Commit Your Changes

```bash
# Stage changes
git add .

# Commit with a clear message
git commit -m "Add EU directive reference resolution

- Implement _extract_eu_directives in ReferenceParser
- Add CELEX number construction for directives
- Include test cases for common directive formats
- Update documentation

Closes #123"
```

**Commit message guidelines:**
- First line: imperative mood, max 72 characters
- Blank line
- Detailed description (what and why, not how)
- Reference issues: "Closes #123", "Fixes #456", "Relates to #789"

### Step 7: Push and Create Pull Request

```bash
# Push to your fork
git push origin feature/your-feature-name

# Go to GitHub and create a Pull Request
```

**Pull Request checklist:**
- [ ] Tests pass (`pytest tests/`)
- [ ] Code is linted (`ruff check`)
- [ ] Documentation is updated
- [ ] Commit messages are clear
- [ ] PR description explains the change
- [ ] Related issues are referenced

---

## Code Style

### Python Style

We use **Ruff** for linting and formatting (enforces PEP 8 + more).

**Key conventions:**
- **Line length**: 100 characters (configured in `pyproject.toml`)
- **Indentation**: 4 spaces (no tabs)
- **Imports**: Sorted with `isort`
- **Docstrings**: Google style
- **Type hints**: Encouraged for public APIs

**Example:**

```python
from __future__ import annotations

from datetime import date
from typing import List, Optional

from lexsr.core.models import Work, Expression


def get_expression_at_date(
    work_id: str,
    query_date: date,
) -> Optional[Expression]:
    """
    Find the Expression of a Work that was valid on a specific date.

    Args:
        work_id: The canonical ID of the Work.
        query_date: The date for which to retrieve the valid version.

    Returns:
        The Expression valid on query_date, or None if the Work
        did not exist at that time.

    Example:
        >>> expr = get_expression_at_date("arbeidswet-1963", date(2024, 1, 15))
        >>> print(expr.version_date)
        2024-01-15
    """
    # Implementation...
```

### File Naming

- **Modules**: lowercase with underscores: `citation_resolver.py`
- **Classes**: PascalCase: `CitationResolver`
- **Functions/variables**: snake_case: `resolve_reference`
- **Constants**: UPPER_SNAKE_CASE: `DEFAULT_JURISDICTION`

### Directory Structure

```
src/lexsr/
  core/           # Core data model and utilities
  ingestion/      # Data ingestion pipelines
  search/         # Search and retrieval
  graph/          # Citation and knowledge graphs
  api/            # REST API
  evaluation/     # Quality metrics and benchmarks
  improvement/    # Active learning and monitoring
```

---

## Testing

### Writing Tests

- Use `pytest` for all tests
- Aim for >80% code coverage
- Test both happy paths and edge cases
- Use fixtures for common test data

**Example test:**

```python
import pytest
from datetime import date

from lexsr.core.models import Work, Expression, SourceType, DocumentStatus
from lexsr.core.store import CanonicalStore


@pytest.fixture
def store(tmp_path):
    """Create a temporary canonical store for testing."""
    db_path = tmp_path / "test.db"
    return CanonicalStore(str(db_path))


@pytest.fixture
def sample_work():
    """Create a sample Work for testing."""
    return Work(
        id="test-law",
        uri="/id/law/test-law",
        source_type=SourceType.LEGISLATION,
        official_id="test-law",
        title="Test Law",
        jurisdiction="SR",
        status=DocumentStatus.IN_FORCE,
    )


def test_save_and_retrieve_work(store, sample_work):
    """Test that we can save and retrieve a Work."""
    # Save
    store.save_work(sample_work)

    # Retrieve
    retrieved = store.get_work_by_uri("/id/law/test-law")

    # Assert
    assert retrieved is not None
    assert retrieved.id == sample_work.id
    assert retrieved.title == sample_work.title


def test_temporal_query(store, sample_work):
    """Test point-in-time queries."""
    # Set up: create work and two expressions
    store.save_work(sample_work)

    expr_2022 = Expression(
        id="test-law-2022",
        uri="/id/law/test-law/2022-01-01",
        work_id="test-law",
        work_uri="/id/law/test-law",
        version_date=date(2022, 1, 1),
    )
    expr_2024 = Expression(
        id="test-law-2024",
        uri="/id/law/test-law/2024-01-01",
        work_id="test-law",
        work_uri="/id/law/test-law",
        version_date=date(2024, 1, 1),
    )

    store.save_expression(expr_2022)
    store.save_expression(expr_2024)

    # Query: what was valid on 2023-06-15?
    result = store.get_expression_at_date("test-law", date(2023, 6, 15))

    # Should return 2022 version (latest before query date)
    assert result is not None
    assert result.id == "test-law-2022"
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_core.py -v

# Run specific test function
pytest tests/test_core.py::test_save_and_retrieve_work -v

# Run with coverage
pytest tests/ --cov=src/lexsr --cov-report=html

# Open coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

---

## Documentation

### Docstring Style

Use **Google style** docstrings:

```python
def resolve_reference(
    raw_text: str,
    version_date: Optional[date] = None,
) -> ResolvedReference:
    """
    Resolve a single legal reference to a canonical URI.

    This function extracts a legal reference from raw text and attempts
    to resolve it to a canonical fragment URI using multi-pass extraction
    and contextual disambiguation.

    Args:
        raw_text: The text containing a legal reference, e.g.,
            "artikel 4 lid 2 Arbeidswet 1963".
        version_date: Optional date for version resolution. If provided,
            the URI will point to the version valid on this date.
            Defaults to today.

    Returns:
        A ResolvedReference object containing:
            - uri: Canonical fragment URI (if resolved)
            - ref_type: Type of reference (legislation, ECLI, etc.)
            - confidence: Confidence score (0.0 to 1.0)
            - status: Resolution status (resolved, partial, unresolved)

    Raises:
        ValueError: If raw_text is empty or invalid.

    Example:
        >>> ref = resolve_reference("artikel 5 Grondwet")
        >>> print(ref.uri)
        /id/law/grondwet-1987/2026-02-14/article/5
        >>> print(ref.confidence)
        0.85
    """
```

### README Updates

When adding new features:
1. Update the main README.md
2. Add usage examples
3. Update the roadmap section
4. Document any new dependencies

### Architecture Documentation

For significant changes:
1. Update `docs/architecture.md`
2. Add diagrams if helpful (use Mermaid or ASCII art)
3. Explain design decisions and trade-offs

---

## Review Process

### Pull Request Review

All PRs require:
1. **Code review** from at least one maintainer
2. **All tests passing** in CI
3. **No linting errors**
4. **Documentation updated**

Reviewers will check for:
- Correctness: Does it work as intended?
- Quality: Is the code clean and maintainable?
- Testing: Are there adequate tests?
- Documentation: Is it well-documented?
- Design: Does it fit the architecture?

### Review Timeline

- **Initial response**: Within 48 hours
- **Full review**: Within 1 week
- **Merge**: When approved and CI passes

---

## Priority Areas

We especially welcome contributions in these areas:

### High Priority
1. **OCR Pipeline**: DeepSeek integration for scanned PDFs
2. **Web Scrapers**: wetten.sr, DNA.sr, gazette sources
3. **Hybrid Search**: RuVector implementation (BM25 + vector + reranking)
4. **Citation Graph**: Build and visualize citation relationships
5. **Test Coverage**: Expand test suite to >90%

### Medium Priority
6. **Entity Extraction**: Courts, organizations, persons
7. **Static Site Generator**: GitHub Pages deployment
8. **Multilingual Support**: English translation interface
9. **API Documentation**: Interactive examples and tutorials
10. **Performance**: Optimization and benchmarking

### Nice to Have
11. **SPARQL Endpoint**: For semantic web integration
12. **Mobile App**: React Native or Flutter
13. **Admin Dashboard**: Web-based management interface
14. **Visualization**: Amendment timelines, citation graphs

---

## Coding for Legal Domain

### Legal-Specific Guidelines

1. **Preserve Legal Structure**: Never chunk arbitrarily. Use article/paragraph boundaries.
2. **Temporal Correctness**: Always consider "as of date" for legislation.
3. **Provenance**: Every derived product must trace back to original source.
4. **Confidence Scores**: Use for all ML/NLP outputs (OCR, entity extraction, citations).
5. **Human Review**: Design workflows for expert validation of critical data.

### Common Pitfalls

❌ **DON'T**: Use arbitrary token-window chunking for legal text
✅ **DO**: Chunk by article, paragraph, or other structural boundaries

❌ **DON'T**: Assume the latest version is always correct
✅ **DO**: Support temporal queries ("what was the law on date X?")

❌ **DON'T**: Silently fail on unresolved citations
✅ **DO**: Queue unresolved references for human review

❌ **DON'T**: Trust OCR output blindly
✅ **DO**: Include OCR confidence scores and allow corrections

---

## Questions?

If you have questions:
1. Check the [README](README.md) and [docs/](docs/)
2. Search existing [issues](https://github.com/your-org/wetten-van-suriname/issues)
3. Ask in [discussions](https://github.com/your-org/wetten-van-suriname/discussions)
4. Tag maintainers in your PR

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License (for code) and CC0 1.0 (for data products).

---

**Thank you for contributing to access to justice in Suriname! 🇸🇷**
