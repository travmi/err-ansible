from subprocess import check_output, STDOUT, CalledProcessError
import pickle
pickle.HIGHEST_PROTOCOL = 2
from rq import Queue, use_connection
from redis import ConnectionError

use_connection()
Q = Queue('ansible')

def run_task(bot, cmd, _from, timeout = 180):
    """
    Runs specified command synchronously (if Redis is running) or
    asynchronously (this is not recommended for production use since the whole
    bot will be blocked until a command returns.
    """

    bot.log.debug("Running {}".format(cmd))
    async = True
    try:
        task = Q.enqueue(check_output, cmd, stderr=STDOUT,
                         timeout=timeout, ttl=60)
        tasklist = bot['tasks']
        tasklist[task.get_id()] = _from
        bot['tasks'] = tasklist
        return "Task '{}' enqueued as {}".format(str(_from), task.get_id())
    except ConnectionError:
        bot.log.error("Error connecting to Redis, falling back to synchronous execution")
        async = False
    if not async:
        # notify also chatrooms and/or bot admins
        bot.send(_from, "Running the task synchronously, whole bot blocked now, please wait.")
        try:
            raw_result = check_output(cmd, stderr=STDOUT)
        except CalledProcessError as exc:
            raw_result = exc.output
        except OSError:
            raw_result = "*ERROR*: ansible-playbook command not found"
        return raw_result

def get_task_info(uuid):
    """
    Gets task info by it's UUID
    """

    task = Q.fetch_job(uuid)
    try:
      res = task.result
      status = task.status
    except AttributeError:
      res = None
      status = 'unknown'
    return (res, status)

def handle_task_exception(task, exc_type, exc_value, traceback):
    """
    Custom RQ exception handler
    Most of the time we care about real Ansible output - thus we mangle with the
    "result" field here. RQ stores result as pickled object - we do the same
    here.
    """
    output = exc_value.output
    task_id = task.get_id()
    redis = task.connection
    redis.hset("rq:job:{}".format(task_id), 'result', pickle.dumps(output))


