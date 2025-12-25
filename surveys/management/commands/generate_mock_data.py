"""
Management command to generate comprehensive mock data for testing.

Usage:
    python manage.py generate_mock_data
    python manage.py generate_mock_data --surveys 5 --responses 50
    python manage.py generate_mock_data --clear
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import random
import secrets

from surveys.models import Survey, Section, Field, FieldOption, ConditionalLogic
from responses.models import SurveyResponse, SurveyResponseItem
from rbac.models import Permission, Role, UserRole
from audits.models import AuditLog


class Command(BaseCommand):
    help = 'Generate mock data for testing the survey platform'

    def add_arguments(self, parser):
        parser.add_argument(
            '--surveys',
            type=int,
            default=3,
            help='Number of surveys to create'
        )
        parser.add_argument(
            '--responses',
            type=int,
            default=20,
            help='Number of responses per survey'
        )
        parser.add_argument(
            '--users',
            type=int,
            default=10,
            help='Number of users to create'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before generating'
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write(self.style.WARNING('Clearing existing data...'))
            self.clear_data()
        
        self.stdout.write(self.style.SUCCESS('Starting mock data generation...'))
        
        # Create users
        users = self.create_users(options['users'])
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(users)} users'))
        
        # Create permissions and roles
        permissions = self.create_permissions()
        roles = self.create_roles(permissions)
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(permissions)} permissions and {len(roles)} roles'))
        
        # Assign roles to users
        self.assign_roles(users, roles)
        self.stdout.write(self.style.SUCCESS('✓ Assigned roles to users'))
        
        # Create surveys
        surveys = self.create_surveys(users, options['surveys'])
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(surveys)} surveys'))
        
        # Create responses
        total_responses = 0
        for survey in surveys:
            responses = self.create_responses(survey, users, options['responses'])
            total_responses += len(responses)
        self.stdout.write(self.style.SUCCESS(f'✓ Created {total_responses} responses'))
        
        # Create audit logs
        logs = self.create_audit_logs(users, surveys)
        self.stdout.write(self.style.SUCCESS(f'✓ Created {len(logs)} audit logs'))
        
        self.stdout.write(self.style.SUCCESS('\n✓ Mock data generation completed!'))
        self.print_summary(users, surveys, total_responses)

    def clear_data(self):
        """Clear all existing data"""
        SurveyResponse.objects.all().delete()
        SurveyResponseItem.objects.all().delete()
        Survey.objects.all().delete()
        UserRole.objects.all().delete()
        Role.objects.all().delete()
        Permission.objects.all().delete()
        AuditLog.objects.all().delete()
        User.objects.exclude(is_superuser=True).delete()

    def create_users(self, count):
        """Create test users"""
        users = []
        
        # Create admin user if doesn't exist
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@example.com',
                'is_staff': True,
                'is_superuser': True,
                'first_name': 'Admin',
                'last_name': 'User'
            }
        )
        if created:
            admin.set_password('admin123')
            admin.save()
        users.append(admin)
        
        # Create regular users
        first_names = ['John', 'Jane', 'Alice', 'Bob', 'Charlie', 'Diana', 'Eve', 'Frank', 'Grace', 'Henry']
        last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
        
        for i in range(count):
            first = random.choice(first_names)
            last = random.choice(last_names)
            username = f'{first.lower()}.{last.lower()}{i}'
            
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@example.com',
                    'first_name': first,
                    'last_name': last,
                }
            )
            if created:
                user.set_password('password123')
                user.save()
            users.append(user)
        
        return users

    def create_permissions(self):
        """Create system permissions"""
        permission_data = [
            # Survey permissions
            ('survey.create', 'Create Survey', 'Can create new surveys'),
            ('survey.view', 'View Survey', 'Can view surveys'),
            ('survey.edit', 'Edit Survey', 'Can edit surveys'),
            ('survey.delete', 'Delete Survey', 'Can delete surveys'),
            ('survey.publish', 'Publish Survey', 'Can publish surveys'),
            # Response permissions
            ('response.create', 'Create Response', 'Can submit responses'),
            ('response.view', 'View Response', 'Can view responses'),
            ('response.view_own', 'View Own Response', 'Can view own responses'),
            ('response.edit', 'Edit Response', 'Can edit responses'),
            ('response.delete', 'Delete Response', 'Can delete responses'),
            # Analytics permissions
            ('analytics.view', 'View Analytics', 'Can view analytics'),
            ('analytics.export', 'Export Analytics', 'Can export analytics data'),
            # User management
            ('user.manage', 'Manage Users', 'Can manage users and roles'),
        ]
        
        permissions = []
        for codename, name, description in permission_data:
            permission, _ = Permission.objects.get_or_create(
                codename=codename,
                defaults={
                    'name': name,
                    'description': description,
                    'is_system_permission': True
                }
            )
            permissions.append(permission)
        
        return permissions

    def create_roles(self, permissions):
        """Create roles and assign permissions"""
        roles_data = {
            'Admin': {
                'description': 'Full system access',
                'permissions': [p.codename for p in permissions]
            },
            'Survey Creator': {
                'description': 'Can create and manage surveys',
                'permissions': ['survey.create', 'survey.view', 'survey.edit', 'survey.publish', 'response.view', 'analytics.view']
            },
            'Analyst': {
                'description': 'Can view surveys and analytics',
                'permissions': ['survey.view', 'response.view', 'analytics.view', 'analytics.export']
            },
            'Respondent': {
                'description': 'Can submit survey responses',
                'permissions': ['response.create', 'response.view_own']
            }
        }
        
        roles = []
        for role_name, role_config in roles_data.items():
            role, _ = Role.objects.get_or_create(
                name=role_name,
                tenant_id='default',
                defaults={
                    'description': role_config['description'],
                    'is_system_role': True
                }
            )
            
            # Assign permissions
            for perm_codename in role_config['permissions']:
                try:
                    perm = Permission.objects.get(codename=perm_codename)
                    role.permissions.add(perm)
                except Permission.DoesNotExist:
                    pass
            
            roles.append(role)
        
        return roles

    def assign_roles(self, users, roles):
        """Assign roles to users"""
        admin_role = next((r for r in roles if r.name == 'Admin'), None)
        creator_role = next((r for r in roles if r.name == 'Survey Creator'), None)
        analyst_role = next((r for r in roles if r.name == 'Analyst'), None)
        respondent_role = next((r for r in roles if r.name == 'Respondent'), None)
        
        for user in users:
            if user.is_superuser:
                UserRole.objects.get_or_create(
                    user=user,
                    role=admin_role,
                    defaults={'tenant_id': 'default'}
                )
            else:
                # Randomly assign roles
                role = random.choice([creator_role, analyst_role, respondent_role])
                UserRole.objects.get_or_create(
                    user=user,
                    role=role,
                    defaults={'tenant_id': 'default'}
                )

    def create_surveys(self, users, count):
        """Create surveys with sections, fields, and logic"""
        survey_templates = [
            {
                'title': 'Customer Satisfaction Survey',
                'description': 'Help us improve our services by sharing your feedback',
                'sections': [
                    {
                        'title': 'General Information',
                        'fields': [
                            {'label': 'How satisfied are you with our service?', 'type': 'rating', 'required': True},
                            {'label': 'How likely are you to recommend us?', 'type': 'slider', 'required': True},
                            {'label': 'What could we improve?', 'type': 'textarea', 'required': False},
                        ]
                    },
                    {
                        'title': 'Product Quality',
                        'fields': [
                            {'label': 'Rate product quality', 'type': 'rating', 'required': True},
                            {'label': 'What products did you purchase?', 'type': 'multiple_choice', 'required': True,
                             'options': ['Product A', 'Product B', 'Product C', 'Product D']},
                        ]
                    }
                ]
            },
            {
                'title': 'Employee Engagement Survey',
                'description': 'Share your thoughts about your work environment',
                'sections': [
                    {
                        'title': 'Work Environment',
                        'fields': [
                            {'label': 'Are you satisfied with your work environment?', 'type': 'boolean', 'required': True},
                            {'label': 'If no, what needs improvement?', 'type': 'textarea', 'required': False},
                            {'label': 'Rate work-life balance', 'type': 'rating', 'required': True},
                        ]
                    },
                    {
                        'title': 'Team Collaboration',
                        'fields': [
                            {'label': 'How well does your team collaborate?', 'type': 'single_choice', 'required': True,
                             'options': ['Very Well', 'Well', 'Neutral', 'Poorly', 'Very Poorly']},
                            {'label': 'Your email', 'type': 'email', 'required': True},
                        ]
                    }
                ]
            },
            {
                'title': 'Event Feedback Survey',
                'description': 'Tell us about your event experience',
                'sections': [
                    {
                        'title': 'Event Details',
                        'fields': [
                            {'label': 'Which event did you attend?', 'type': 'dropdown', 'required': True,
                             'options': ['Tech Conference 2025', 'Product Launch', 'Annual Summit']},
                            {'label': 'Event date', 'type': 'date', 'required': True},
                            {'label': 'Overall rating', 'type': 'rating', 'required': True},
                        ]
                    }
                ]
            }
        ]
        
        surveys = []
        for i in range(count):
            template = random.choice(survey_templates)
            creator = random.choice(users)
            
            # Create survey
            survey = Survey.objects.create(
                title=template['title'] + f' #{i+1}',
                description=template['description'],
                status=random.choice(['draft', 'published', 'published', 'published']),  # More published
                version=1,
                created_by=creator,
                tenant_id='default',
                allow_multiple_submissions=random.choice([True, False]),
                allow_partial_submissions=True,
                submission_deadline=timezone.now() + timedelta(days=random.randint(7, 90))
            )
            
            # Create sections and fields
            for section_idx, section_data in enumerate(template['sections']):
                section = Section.objects.create(
                    survey=survey,
                    title=section_data['title'],
                    description='',
                    order=section_idx
                )
                
                for field_idx, field_data in enumerate(section_data['fields']):
                    field = Field.objects.create(
                        section=section,
                        label=field_data['label'],
                        field_type=field_data['type'],
                        order=field_idx,
                        is_required=field_data.get('required', False),
                        config=self.get_field_config(field_data['type'])
                    )
                    
                    # Create options for choice fields
                    if 'options' in field_data:
                        for opt_idx, option_label in enumerate(field_data['options']):
                            FieldOption.objects.create(
                                field=field,
                                label=option_label,
                                value=option_label.lower().replace(' ', '_'),
                                order=opt_idx
                            )
            
            surveys.append(survey)
        
        return surveys

    def get_field_config(self, field_type):
        """Get field-specific configuration"""
        configs = {
            'rating': {'min': 1, 'max': 5, 'icon': 'star'},
            'slider': {'min': 0, 'max': 100, 'step': 10},
            'number': {'min': 0, 'max': 1000},
        }
        return configs.get(field_type, {})

    def create_responses(self, survey, users, count):
        """Create survey responses with field responses"""
        if survey.status != 'published':
            return []
        
        responses = []
        fields = Field.objects.filter(section__survey=survey).select_related('section')
        
        for i in range(count):
            user = random.choice(users) if random.random() > 0.3 else None  # 30% anonymous
            status = random.choices(
                ['completed', 'completed', 'completed', 'in_progress', 'abandoned'],
                weights=[50, 30, 10, 7, 3]
            )[0]
            
            # Create response
            response = SurveyResponse.objects.create(
                survey=survey,
                user=user,
                respondent_email=f'respondent{i}@example.com' if not user else '',
                status=status,
                ip_address=f'192.168.{random.randint(1, 255)}.{random.randint(1, 255)}',
                user_agent='Mozilla/5.0 (Test Browser)',
                started_at=timezone.now() - timedelta(hours=random.randint(1, 48)),
                submitted_at=timezone.now() - timedelta(hours=random.randint(0, 24)) if status == 'completed' else None,
                resume_token=secrets.token_urlsafe(32),
                tenant_id='default'
            )
            
            # Create field responses
            for field in fields:
                # Skip some fields for in_progress/abandoned
                if status != 'completed' and random.random() > 0.7:
                    continue
                
                value = self.generate_field_value(field)
                if value is not None:
                    item = SurveyResponseItem.objects.create(
                        response=response,
                        field=field
                    )
                    item.set_value(value)
                    item.save()
            
            responses.append(response)
        
        return responses

    def generate_field_value(self, field):
        """Generate appropriate value for field type"""
        field_type = field.field_type
        
        if field_type == 'text':
            return random.choice(['Great', 'Good', 'Excellent', 'Amazing', 'Perfect'])
        elif field_type == 'textarea':
            return random.choice([
                'The service was excellent and exceeded my expectations.',
                'Good overall experience, but could be improved.',
                'Everything was fine, no major issues.',
                'Very satisfied with the quality and support.',
            ])
        elif field_type == 'number':
            return random.randint(1, 100)
        elif field_type == 'email':
            return f'user{random.randint(1, 1000)}@example.com'
        elif field_type == 'phone':
            return f'+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}'
        elif field_type == 'date':
            return (timezone.now() - timedelta(days=random.randint(0, 365))).date().isoformat()
        elif field_type == 'datetime':
            return (timezone.now() - timedelta(hours=random.randint(0, 8760))).isoformat()
        elif field_type == 'boolean':
            return random.choice([True, False])
        elif field_type == 'rating':
            return random.randint(1, 5)
        elif field_type == 'slider':
            return random.randint(0, 100)
        elif field_type in ['single_choice', 'dropdown']:
            options = field.options.all()
            return random.choice(options).value if options else None
        elif field_type == 'multiple_choice':
            options = list(field.options.all())
            selected = random.sample(options, k=random.randint(1, min(3, len(options))))
            return [opt.value for opt in selected]
        
        return 'Sample value'

    def create_audit_logs(self, users, surveys):
        """Create audit log entries"""
        actions = [
            ('CREATE', 'Survey created'),
            ('UPDATE', 'Survey published'),
            ('UPDATE', 'Survey updated'),
            ('CREATE', 'Response submitted'),
        ]
        
        logs = []
        for i in range(50):
            action, description = random.choice(actions)
            user = random.choice(users)
            survey = random.choice(surveys)
            
            log = AuditLog.objects.create(
                user=user,
                username=user.username,
                action=action,
                resource_type='survey',
                resource_id=str(survey.id),
                description=f'{description}: {survey.title}',
                ip_address=f'192.168.{random.randint(1, 255)}.{random.randint(1, 255)}',
                user_agent='Mozilla/5.0 (Test Browser)',
                tenant_id='default',
                new_values={'status': 'published'} if 'published' in description else {}
            )
            logs.append(log)
        
        return logs

    def print_summary(self, users, surveys, responses):
        """Print summary of generated data"""
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS('MOCK DATA SUMMARY'))
        self.stdout.write('='*50)
        self.stdout.write(f'Users: {len(users)}')
        self.stdout.write(f'Surveys: {len(surveys)}')
        self.stdout.write(f'  - Published: {len([s for s in surveys if s.status == "published"])}')
        self.stdout.write(f'  - Draft: {len([s for s in surveys if s.status == "draft"])}')
        self.stdout.write(f'Responses: {responses}')
        self.stdout.write('\nTest credentials:')
        self.stdout.write('  Username: admin')
        self.stdout.write('  Password: admin123')
        self.stdout.write('='*50 + '\n')
