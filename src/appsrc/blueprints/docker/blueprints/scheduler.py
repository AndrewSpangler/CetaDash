from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
import queue
import logging
import atexit
import threading
from tzlocal import get_localzone
from ..models import app, ScheduleTrigger, Workflow, WorkflowTaskAssociation, SYSTEM_ID
from .trigger_handling import handle_trigger


def activate_trigger(trigger_id):
    with app.app_context():
        result_queue = queue.Queue()
        trigger = ScheduleTrigger.query.get(trigger_id)
        if not trigger:
            logging.error(f"Trigger {trigger_id} not found")
            return
        
        workflow = Workflow.query.get(trigger.workflow_id)
        if not workflow:
            logging.error(f"Workflow {trigger.workflow_id} not found for trigger {trigger_id}")
            return
            
        tasks = [
            assoc.task for assoc in 
            workflow.task_associations.order_by(
                WorkflowTaskAssociation.priority.asc()
            )
        ]
        thread = threading.Thread(
            target=handle_trigger,
            args=(SYSTEM_ID, trigger, {}, workflow, tasks, result_queue, True),
            daemon=False
        )
        thread.start()
        thread.join()
        return


class WorkflowScheduler:
    """Scheduler class to manage scheduled tasks using APScheduler"""
    
    def __init__(self, app):
        self.app = app
        self.scheduler = None
        self.logger = logging.getLogger(__name__)
        
        db_url = app.config.get('SQLALCHEMY_BINDS', {}).get('cetadash_db')
        if not db_url:
            raise ValueError("Database not found")

        self.scheduler = BackgroundScheduler(
            jobstores={'default': SQLAlchemyJobStore(url=db_url)},
            executors={'default': ThreadPoolExecutor(20)},
            job_defaults={'coalesce': False, 'max_instances': 3},
            timezone=get_localzone()
        )
        self.scheduler.add_listener(self._job_executed, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(self._job_error, EVENT_JOB_ERROR)
        self.scheduler.start()
        self.logger.info("Scheduler started")
        atexit.register(self.shutdown)
    
    def _job_executed(self, event):
        """Event listener for successful job execution"""
        self.logger.info(f"Job {event.job_id} executed successfully")
    
    def _job_error(self, event):
        """Event listener for job execution errors"""
        self.logger.error(f"Job {event.job_id} failed: {event.exception}")
    
    def add_schedule_trigger(self, trigger):
        """Add a ScheduleTrigger to the scheduler"""
        if not trigger.enabled:
            self.logger.info(f"Skipping disabled trigger {trigger.id}")
            return
        
        job_id = f"trigger_{trigger.id}"

        # Remove existing job if it exists
        try:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
        except Exception as e:
            self.logger.warning(f"Error removing existing job {job_id}: {e}")
        
        try:
            if trigger.job_type == "cron":
                self._add_cron_job(trigger, job_id)
            elif trigger.job_type == "interval":
                self._add_interval_job(trigger, job_id)
            else:
                self.logger.error(f"Unknown job type: {trigger.job_type}")
                return
            
            self.logger.info(f"Added scheduled trigger {trigger.id} with job_id {job_id}")
            
        except Exception as e:
            import traceback
            self.logger.error(f"Failed to add trigger {trigger.id}: {str(e)}")
            traceback.print_exc()
    
    def _add_cron_job(self, trigger, job_id):
        """Add a cron-based scheduled job"""
        cron_kwargs = {}
        
        if trigger.day_of_week is not None and trigger.day_of_week.strip():
            cron_kwargs['day_of_week'] = trigger.day_of_week
        if trigger.hour is not None and str(trigger.hour).strip():
            cron_kwargs['hour'] = trigger.hour
        if trigger.minute is not None and str(trigger.minute).strip():
            cron_kwargs['minute'] = trigger.minute
        
        self.logger.info(f"Adding cron job with kwargs: {cron_kwargs}")
        
        self.scheduler.add_job(
            func=activate_trigger,
            trigger='cron',
            args=[trigger.id],
            id=job_id,
            name=f"Cron Trigger: {trigger.name}",
            replace_existing=True,
            **cron_kwargs
        )
    
    def _add_interval_job(self, trigger, job_id):
        """Add an interval-based scheduled job"""
        interval_kwargs = {}
        
        if trigger.seconds is not None and trigger.seconds > 0:
            interval_kwargs['seconds'] = trigger.seconds
        if trigger.minutes is not None and trigger.minutes > 0:
            interval_kwargs['minutes'] = trigger.minutes
        if trigger.hours is not None and trigger.hours > 0:
            interval_kwargs['hours'] = trigger.hours

        if not interval_kwargs:
            self.logger.error(f"No valid interval specified for trigger {trigger.id}")
            return
        
        self.logger.info(f"Adding interval job with kwargs: {interval_kwargs}")
        
        self.scheduler.add_job(
            func=activate_trigger,
            trigger='interval',
            args=[trigger.id],
            id=job_id,
            name=f"Interval Trigger: {trigger.name}",
            replace_existing=True,
            **interval_kwargs
        )
    
    def remove_trigger(self, trigger_id):
        """Remove a scheduled trigger"""
        job_id = f"trigger_{trigger_id}"
        
        try:
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                self.logger.info(f"Removed scheduled trigger {trigger_id}")
            else:
                self.logger.warning(f"Job {job_id} not found")
        except Exception as e:
            self.logger.error(f"Error removing trigger {trigger_id}: {str(e)}")
    
    def update_trigger(self, trigger):
        """Update an existing scheduled trigger"""
        self.remove_trigger(trigger.id)
        if trigger.enabled:
            self.add_schedule_trigger(trigger)
    
    def clear_all_triggers(self):
        """Clear all scheduled triggers - useful for preventing duplicates on reload"""
        try:
            # Get all trigger jobs
            trigger_jobs = [job for job in self.scheduler.get_jobs() if job.id.startswith('trigger_')]
            
            for job in trigger_jobs:
                try:
                    self.scheduler.remove_job(job.id)
                    self.logger.info(f"Removed job {job.id} during clear")
                except Exception as e:
                    self.logger.warning(f"Error removing job {job.id} during clear: {e}")
                    
            self.logger.info(f"Cleared {len(trigger_jobs)} scheduled triggers")
            
        except Exception as e:
            self.logger.error(f"Error clearing triggers: {str(e)}")
    
    def load_all_triggers(self):
        """Load all enabled ScheduleTriggers from database"""
        try:
            self.clear_all_triggers()
            
            with self.app.app_context():
                triggers = ScheduleTrigger.query.filter_by(enabled=True).all()
            
            for trigger in triggers:
                self.add_schedule_trigger(trigger)
            
            self.logger.info(f"Loaded {len(triggers)} scheduled triggers")
            
        except Exception as e:
            self.logger.error(f"Error loading triggers: {str(e)}")
    
    def get_scheduled_jobs(self):
        """Get all currently scheduled jobs"""
        return self.scheduler.get_jobs()
    
    def get_job_info(self, trigger_id):
        """Get information about a specific scheduled job"""
        job_id = f"trigger_{trigger_id}"
        job = self.scheduler.get_job(job_id)
        
        if job:
            return {
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time,
                'trigger': str(job.trigger)
            }
        return None
    
    def pause_trigger(self, trigger_id):
        """Pause a scheduled trigger"""
        job_id = f"trigger_{trigger_id}"
        try:
            self.scheduler.pause_job(job_id)
            self.logger.info(f"Paused trigger {trigger_id}")
        except Exception as e:
            self.logger.error(f"Error pausing trigger {trigger_id}: {str(e)}")
    
    def resume_trigger(self, trigger_id):
        """Resume a paused trigger"""
        job_id = f"trigger_{trigger_id}"
        try:
            self.scheduler.resume_job(job_id)
            self.logger.info(f"Resumed trigger {trigger_id}")
        except Exception as e:
            self.logger.error(f"Error resuming trigger {trigger_id}: {str(e)}")
    
    def reload(self):
        """Reload all scheduled triggers from database without impacting running services"""
        try:
            self.logger.info("Starting scheduler reload...")
            
            with self.app.app_context():
                # Get current scheduled jobs
                current_jobs = {job.id: job for job in self.scheduler.get_jobs()}
                current_trigger_jobs = {job_id: job for job_id, job in current_jobs.items() 
                                      if job_id.startswith('trigger_')}
                
                all_triggers = ScheduleTrigger.query.all()
                expected_jobs = set()
                
                # Process each trigger
                for trigger in all_triggers:
                    job_id = f"trigger_{trigger.id}"
                    expected_jobs.add(job_id)
                    
                    if trigger.enabled:
                        # Check if job needs updating
                        existing_job = current_jobs.get(job_id)
                        
                        if existing_job:
                            # Check if job config changed
                            if self._job_needs_update(trigger, existing_job):
                                self.logger.info(f"Updating changed trigger {trigger.id}")
                                self.remove_trigger(trigger.id)
                                self.add_schedule_trigger(trigger)
                            else:
                                self.logger.debug(f"Trigger {trigger.id} unchanged, keeping existing job")
                        else:
                            # Add new trigger
                            self.logger.info(f"Adding new trigger {trigger.id}")
                            self.add_schedule_trigger(trigger)
                    else:
                        # Trigger is disabled, remove if it exists
                        if existing_job:
                            self.logger.info(f"Removing disabled trigger {trigger.id}")
                            self.remove_trigger(trigger.id)
                
                # Remove orphaned jobs (no longer exist in database)
                for job_id in current_trigger_jobs:
                    if job_id not in expected_jobs:
                        trigger_id = job_id.replace('trigger_', '')
                        self.logger.info(f"Removing orphaned job for trigger {trigger_id}")
                        try:
                            self.scheduler.remove_job(job_id)
                        except Exception as e:
                            self.logger.error(f"Error removing orphaned job {job_id}: {e}")
                
                final_jobs = [job for job in self.scheduler.get_jobs() if job.id.startswith('trigger_')]
                self.logger.info(f"Scheduler reload completed. Active scheduled triggers: {len(final_jobs)}")
                
                return {
                    'success': True,
                    'message': f'Reload completed. {len(final_jobs)} active scheduled triggers.',
                    'active_triggers': len(final_jobs)
                }
            
        except Exception as e:
            import traceback
            self.logger.error(f"Error during scheduler reload: {str(e)}")
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Reload failed: {str(e)}',
                'active_triggers': len([job for job in self.scheduler.get_jobs() if job.id.startswith('trigger_')])
            }
    
    def _job_needs_update(self, trigger, existing_job):
        """Check if a job needs to be updated based on trigger configuration"""
        try:
            # Check if job name changed
            expected_name = f"{trigger.job_type.title()} Trigger: {trigger.name}"
            if existing_job.name != expected_name:
                self.logger.info(f"Job name changed for trigger {trigger.id}: '{existing_job.name}' -> '{expected_name}'")
                return True
            
            # Check job type and configuration
            if trigger.job_type == "cron":
                if not hasattr(existing_job.trigger, 'fields'):
                    self.logger.info(f"Job {existing_job.id} is not a cron job but should be")
                    return True
                
                # Build expected cron fields
                expected_fields = {}
                if trigger.day_of_week is not None and trigger.day_of_week.strip():
                    expected_fields['day_of_week'] = str(trigger.day_of_week)
                if trigger.hour is not None and str(trigger.hour).strip():
                    expected_fields['hour'] = str(trigger.hour)
                if trigger.minute is not None and str(trigger.minute).strip():
                    expected_fields['minute'] = str(trigger.minute)
                
                # Compare with existing fields
                for field_name, expected_value in expected_fields.items():
                    existing_field = existing_job.trigger.fields.get(field_name)
                    if existing_field:
                        existing_value = str(existing_field)
                        if existing_value != expected_value:
                            self.logger.info(f"Cron field {field_name} changed for trigger {trigger.id}: '{existing_value}' -> '{expected_value}'")
                            return True
                    else:
                        self.logger.info(f"Cron field {field_name} missing for trigger {trigger.id}")
                        return True
                
                # Check if existing job has fields that shouldn't be there
                job_field_names = set(existing_job.trigger.fields.keys())
                expected_field_names = set(expected_fields.keys())
                if job_field_names != expected_field_names:
                    self.logger.info(f"Cron fields set changed for trigger {trigger.id}: {job_field_names} -> {expected_field_names}")
                    return True
                    
            elif trigger.job_type == "interval":
                if not hasattr(existing_job.trigger, 'interval'):
                    self.logger.info(f"Job {existing_job.id} is not an interval job but should be")
                    return True
                
                # Calculate expected interval in seconds
                expected_seconds = 0
                if trigger.seconds and trigger.seconds > 0:
                    expected_seconds += trigger.seconds
                if trigger.minutes and trigger.minutes > 0:
                    expected_seconds += trigger.minutes * 60
                if trigger.hours and trigger.hours > 0:
                    expected_seconds += trigger.hours * 3600
                
                if expected_seconds == 0:
                    self.logger.error(f"Invalid interval configuration for trigger {trigger.id}")
                    return True
                

                existing_seconds = existing_job.trigger.interval.total_seconds()
                if abs(existing_seconds - expected_seconds) > 1:  # Allow 1 second tolerance
                    self.logger.info(f"Interval changed for trigger {trigger.id}: {existing_seconds}s -> {expected_seconds}s")
                    return True
            
            return False
            
        except Exception as e:
            self.logger.warning(f"Error checking if job needs update for trigger {trigger.id}: {str(e)}")
            return True
    
    def get_reload_status(self):
        """Get current status of scheduled triggers"""
        try:
            with self.app.app_context():
                total_triggers = ScheduleTrigger.query.count()
                enabled_triggers = ScheduleTrigger.query.filter_by(enabled=True).count()
                scheduled_jobs = [job for job in self.scheduler.get_jobs() if job.id.startswith('trigger_')]
                
                return {
                    'total_triggers_in_db': total_triggers,
                    'enabled_triggers_in_db': enabled_triggers,
                    'active_scheduled_jobs': len(scheduled_jobs),
                    'scheduler_running': self.scheduler.running if self.scheduler else False,
                    'scheduled_jobs': [
                        {
                            'job_id': job.id,
                            'name': job.name,
                            'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                            'trigger_type': type(job.trigger).__name__
                        }
                        for job in scheduled_jobs
                    ]
                }
            
        except Exception as e:
            self.logger.error(f"Error getting reload status: {str(e)}")
            return {
                'error': str(e),
                'scheduler_running': self.scheduler.running if self.scheduler else False
            }

    def shutdown(self):
        """Shutdown the scheduler"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            self.logger.info("Scheduler shut down")