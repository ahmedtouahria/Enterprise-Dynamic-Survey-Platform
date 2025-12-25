# Enterprise Dynamic Survey Platform

## Overview

Enterprise-grade dynamic survey platform built with Django REST Framework, designed for high traffic, complex conditional logic, real-time analytics, and horizontal scalability.

---

## 📚 Documentation

### Getting Started
- **[🚀 Quick Start Guide](QUICKSTART.md)** - Installation and setup instructions
- **[🔐 JWT Authentication Guide](JWT_AUTHENTICATION_GUIDE.md)** - Complete JWT authentication reference

### API Documentation (Survey Builder)
- **[🎉 Delivery Summary](DELIVERY_SUMMARY.md)** - Quick overview of what was delivered
- **[📋 API Implementation Summary](API_IMPLEMENTATION_SUMMARY.md)** - Complete implementation details
- **[📖 API Documentation](API_DOCUMENTATION.md)** - Full REST API reference (1000+ lines)
- **[⚡ API Quick Reference](API_QUICK_REFERENCE.md)** - Quick lookup guide for endpoints
- **[🔄 Complete Workflow Example](COMPLETE_WORKFLOW_EXAMPLE.md)** - Step-by-step survey creation
- **[🧪 API Testing Guide](API_TESTING_GUIDE.md)** - Testing tools and examples
- **[🎨 API Visual Overview](API_VISUAL_OVERVIEW.md)** - Visual diagrams and architecture

### Model Documentation
- **[Models Documentation](MODELS_DOCUMENTATION.md)** - Database models, relationships, and patterns
- **[Implementation Summary](IMPLEMENTATION_SUMMARY.md)** - Project setup and structure
- **[Entity Relationship Diagram](ENTITY_RELATIONSHIP_DIAGRAM.md)** - ASCII ER diagrams
- **[Database Schema Diagram](DB_SCHEMA_DIAGRAM.md)** - Mermaid ER diagram

---

## Architecture Components

### Application Layer
- **Django REST API**: Survey Builder, Submissions, Analytics, Admin (stateless, horizontally scalable)
- **Authentication**: JWT with RBAC (roles: Admin, Survey Creator, Analyst, Respondent)

### Data Layer
- **PostgreSQL**: Master-replica setup with partitioned tables (`submissions`, `audit_logs`)
- **Redis Cluster**: Cache, sessions, rate limiting, Celery queue, partial submissions
- **Object Storage**: File uploads, report exports (S3/MinIO)

### Worker Layer
- **Celery**: Multiple queues (high_priority, analytics, exports, notifications)
- **Celery Beat**: Scheduled tasks for analytics refresh, reminders, archival

### Infrastructure
- **Load Balancer**: Nginx/Traefik with SSL termination and rate limiting
- **Monitoring**: Prometheus, Grafana, ELK/Loki, Sentry

---

## Data Flow

### Survey Creation
```
User → API → Validate → PostgreSQL → Cache Invalidation → Celery Task (logic graph) → Response
```

### Submission
```
User → API → Redis (check partial) → Validate → Evaluate Logic → PostgreSQL
     → Redis (update cache) → [If complete] Celery Tasks → Response
```
- **Partial submissions**: Redis (7-day TTL) + periodic DB sync
- **Resume**: submission_id + HMAC token

### Analytics
```
Dashboard → API → Redis Cache → [Miss] PostgreSQL Replica → Redis (5-60min TTL) → Response
```
- **Real-time**: Pre-aggregated every 5 seconds via Celery
- **Cardinality**: HyperLogLog in Redis

---

## Scaling Strategy

### Horizontal Scaling
- **API**: 2-50 stateless instances, auto-scale on CPU > 70% or latency > 500ms
- **Database**: 2-5 read replicas, write to master only
- **Celery**: Separate pools per queue, auto-scale on queue depth

### Caching
- **L1**: In-memory per instance (256MB, surveys 10min, permissions 5min)
- **L2**: Redis shared (surveys 1hr, analytics 5-60min, sessions 24hr)
- **Invalidation**: Redis pub/sub to all API instances

### Database Optimization
- **Partitioning**: Monthly for `submission_answers` and `audit_logs`
- **Indexes**: B-tree (FKs), GIN (JSON), partial (active surveys only)
- **Pooling**: PgBouncer, max 200 (master), 300 (replicas)

---

## Security

### Authentication & Authorization
- JWT with refresh rotation, stored in Redis
- Multi-tenant isolation via row-level security (RLS)
- RBAC: survey.*, submission.*, analytics.*, user.manage

### Data Protection
- **Encryption**: TLS 1.3 (transit), PostgreSQL TDE (rest), app-level for PII
- **Key Management**: AWS KMS / HashiCorp Vault
- **GDPR**: Soft delete + background purge, configurable retention

### Audit & Rate Limiting
- Append-only audit logs (who, what, when, where, how)
- Rate limits: 100 req/min (authenticated), 20 req/min (anonymous)
- CloudFlare / AWS WAF for DDoS

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **PostgreSQL + JSONB** | ACID guarantees, complex JOINs, JSONB flexibility for conditional rules |
| **Eventual consistency (analytics)** | 5-second lag acceptable, reduces master DB load |
| **Hybrid partial submissions** | Redis (fast) + DB (durable), TTL prevents unbounded growth |
| **Modular monolith** | Faster development, extract services later when bottlenecks identified |
| **Async analytics** | Keeps submission API fast (< 200ms), failures don't block users |

---

## 6. Deployment Architecture

```
                                   ┌─────────────┐
                                   │   Route53   │
                                   │     DNS     │
                                   └──────┬──────┘
                                          │
                                   ┌──────▼──────┐
                                   │  CloudFlare │
                                   │  WAF + CDN  │
                                   └──────┬──────┘
                                          │
                          ┌───────────────┴───────────────┐
                          │   Application Load Balancer   │
                          └───────────────┬───────────────┘
                                          │
                   ┌──────────────────────┼──────────────────────┐
                   │                      │                      │
            ┌──────▼──────┐        ┌─────▼──────┐       ┌──────▼──────┐
            │   Django    │        │   Django   │       │   Django    │
            │   API (1)   │        │   API (2)  │       │   API (N)   │
            └──────┬──────┘        └─────┬──────┘       └──────┬──────┘
                   │                      │                      │
                   └──────────────────────┼──────────────────────┘
                                          │
              ┌───────────────────────────┼───────────────────────────┐
              │                           │                           │
       ┌──────▼──────┐           ┌───────▼───────┐         ┌────────▼────────┐
       │  PostgreSQL │           │  Redis Cluster│         │  Celery Workers │
       │   Master    │           │   (Cache +    │         │  (Analytics,    │
       └──────┬──────┘           │    Queue)     │         │   Exports)      │
              │                  └───────────────┘         └─────────────────┘
       ┌──────▼──────┐
       │  PostgreSQL │
       │  Replicas   │
       └─────────────┘
```

---

## 7. Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Survey load time | < 300ms (p95) | API response time |
| Submission save | < 200ms (p95) | Write operation |
| Partial save (draft) | < 50ms (p95) | Redis write |
| Analytics query | < 1s (p95) | Complex aggregations |
| Concurrent users | 10,000+ | Load testing |
| Submissions/second | 500+ | Burst capacity |
| Database connections | < 80% pool | Connection pooling |

---

## 8. Monitoring & Alerts

**Golden Signals**:
1. **Latency**: p50, p95, p99 for each endpoint
2. **Traffic**: Requests per second, active users
3. **Errors**: Error rate by endpoint and error type
4. **Saturation**: CPU, memory, DB connections, queue depth

**Critical Alerts**:
- API error rate > 1%
- p95 latency > 1s
- Database replica lag > 10s
- Celery queue depth > 1000
- Redis memory > 80%
- Failed authentication rate spike (potential attack)

---

## 9. Future Enhancements

1. **GraphQL API**: More flexible data fetching for complex frontend needs
2. **WebSocket Support**: Real-time collaboration on survey editing
3. **Multi-region Deployment**: Global read replicas for low latency
4. **Event Sourcing**: For complete audit trail and time-travel debugging
5. **ML-based Analytics**: Anomaly detection, sentiment analysis on open-ended responses
6. **Mobile SDKs**: Native iOS/Android libraries for offline-first submissions

---

## Conclusion

This architecture balances immediate business needs with long-term scalability. The modular monolith approach allows rapid development while maintaining clear service boundaries for future extraction. PostgreSQL provides strong consistency where needed, while Redis and async processing enable high throughput. The system is designed to scale horizontally at every layer and can handle 10,000+ concurrent users with proper infrastructure provisioning.

**Estimated Infrastructure Cost** (AWS, moderate usage):
- Compute (ECS/EKS): $800/month
- RDS PostgreSQL (Multi-AZ): $600/month  
- ElastiCache Redis: $200/month
- Load Balancer + Data Transfer: $150/month
- Monitoring & Logging: $100/month
**Total**: ~$1,850/month baseline, scales with traffic

**Development Timeline**:
- Phase 1 (Core MVP): 8 weeks
- Phase 2 (Analytics + RBAC): 4 weeks
- Phase 3 (Optimization + Monitoring): 2 weeks

---

## Technology Stack

### Backend
- **Framework**: Django 5.0+ with Django REST Framework
- **Language**: Python 3.11+
- **API**: RESTful with OpenAPI/Swagger documentation

### Database
- **Primary**: PostgreSQL 15+ with JSONB support
- **Cache/Queue**: Redis 7+ (Cluster mode)
- **Search**: PostgreSQL Full-Text Search (or Elasticsearch for advanced needs)

### Task Queue
- **Worker**: Celery 5+
- **Broker**: Redis
- **Result Backend**: Redis
- **Scheduler**: Celery Beat

### Infrastructure
- **Container**: Docker + Docker Compose
- **Orchestration**: Kubernetes (production) or ECS
- **Proxy**: Nginx or Traefik
- **CI/CD**: GitHub Actions / GitLab CI

### Monitoring
- **Metrics**: Prometheus + Grafana
- **Logging**: ELK Stack or Loki
- **APM**: Sentry or New Relic
- **Uptime**: UptimeRobot or Pingdom

---

## Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose (optional)

### Local Development Setup

1. Clone the repository
```bash
git clone <repository-url>
cd Enterprise-Dynamic-Survey-Platform
```

2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Configure environment variables
```bash
cp .env.example .env
# Edit .env with your database and Redis credentials
```

5. Run migrations
```bash
python manage.py migrate
```

6. Create superuser
```bash
python manage.py createsuperuser
```

7. Start development server
```bash
python manage.py runserver
```

8. Start Celery worker (in separate terminal)
```bash
celery -A config worker -l info
```

9. Start Celery beat (in separate terminal)
```bash
celery -A config beat -l info
```

### Docker Setup

```bash
docker-compose up -d
```

This will start:
- Django API (port 8000)
- PostgreSQL (port 5432)
- Redis (port 6379)
- Celery Worker
- Celery Beat

---

## API Documentation

Once the server is running, access the API documentation at:
- **Swagger UI**: http://localhost:8000/api/docs/
- **ReDoc**: http://localhost:8000/api/redoc/

---


