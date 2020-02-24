import pathlib
from typing import Dict, List

import _judger
import os
from exception import CompileError, JudgeServiceError

default_env = ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"]


class JudgerBridge:
    def __init__(self):
        self._max_output_size = 32 * 1024 * 1024  # 30M
        self._max_process_number = 1
        self._uid = self._gid = 0
        self._env = default_env
        self._max_cpu_time = None
        self._max_memory = None
        self._exe_path = None
        self._args = None
        self._seccomp_rule_name = None
        self._memory_limit_check_only = None

    @property
    def _max_real_time(self):
        return 3 * self._max_cpu_time if self._max_cpu_time else None

    def __str__(self) -> str:
        return self.__dict__.__str__()


class Compiler(JudgerBridge):
    def __init__(self, command: str, base_dir: str):
        super().__init__()
        self._max_cpu_time = 10000
        self._max_memory = 128 * 1024 * 1024  # 128MB
        self._max_stack = 128 * 1024 * 1024
        self._memory_limit_check_only = 0
        self.command = command
        if command.find('java') >= 0:
            self._max_memory = -1
            self._max_cpu_time *= 2
        self.base_dir = base_dir

    def __call__(self) -> None:
        os.chdir(self.base_dir)
        compiler_out = "compiler_output.log"
        _command = self.command.split(" ")
        result = _judger.run(max_cpu_time=self._max_cpu_time,
                             max_real_time=self._max_real_time,
                             max_memory=self._max_memory,
                             max_stack=256 * 1024 * 1024,
                             max_output_size=-1,
                             max_process_number=-1,
                             exe_path=_command[0],
                             # /dev/null is best, but in some system, this will call ioctl system call
                             input_path='/dev/null',
                             output_path=compiler_out,
                             error_path=compiler_out,
                             args=_command[1::],
                             env=default_env,
                             log_path='compiler.log',
                             seccomp_rule_name=None,
                             uid=0,
                             gid=0)
        if result["result"] != _judger.RESULT_SUCCESS:
            if os.path.exists(compiler_out):
                with open(compiler_out, encoding="utf-8") as f:
                    error = f.read().strip()
                    if error:
                        raise CompileError(error)
            print(result)
            raise CompileError("Compiler runtime error, info: System Broken")


class Judger(JudgerBridge):
    def __init__(self,
                 max_cpu_time,
                 max_memory,
                 command,
                 seccomp_rule,
                 judge_dir,
                 memory_limit_check_only,
                 data_dir, submit_id,
                 spj):
        super().__init__()
        self.submit_id = submit_id
        self.judge_dir = judge_dir
        self.data_dir = data_dir
        self._max_cpu_time = max_cpu_time
        self._max_memory = max_memory
        if str(command).find('java') >= 0:
            self._max_memory = -1
            self._max_cpu_time *= 2
        elif str(command).find('py') >= 0:
            self._max_memory *= 2
            self._max_cpu_time *= 2
        command = command.split(' ')
        self._exe_path = command[0]
        self._args = command[1:]
        self._args.append('-XX:MaxRAM=' + str(max_memory))
        self._seccomp_rule_name = seccomp_rule
        self._memory_limit_check_only = memory_limit_check_only
        self.spj = spj

    def __call__(self) -> List[Dict]:
        os.chdir(self.judge_dir)
        datas = pathlib.Path(self.data_dir)
        results = []
        for data in datas.glob("*.in"):
            case_id = data.stem
            output_path = case_id + ".out"
            err_path = case_id + ".err"
            input_path = str(data.absolute())
            run_result = _judger.run(max_cpu_time=self._max_cpu_time,
                                     max_real_time=self._max_real_time,
                                     max_memory=self._max_memory,
                                     max_stack=256 * 1024 * 1024,
                                     max_output_size=self._max_output_size,
                                     max_process_number=1,
                                     exe_path=self._exe_path,
                                     input_path=input_path,
                                     output_path=output_path,
                                     error_path=err_path,
                                     args=self._args,
                                     env=default_env,
                                     log_path="judger.log",
                                     seccomp_rule_name=self._seccomp_rule_name,
                                     uid=0,
                                     gid=0,
                                     memory_limit_check_only=self._memory_limit_check_only,
                                     )
            if run_result['result'] != _judger.RESULT_SUCCESS:
                results.append(run_result)
                return results
            if not self.compare(case_id):
                run_result['result'] = _judger.RESULT_WRONG_ANSWER
                results.append(run_result)
                return results
            results.append(run_result)
        return results

    def compare(self, case_id):
        os.chdir(self.judge_dir)
        if self.spj:
            return self.special_judge(case_id)
        try:
            with open(os.path.join(self.data_dir, case_id + ".out")) as ans:
                with open(case_id + ".out") as uans:
                    line1 = ans.readlines()
                    line2 = uans.readlines()
                    if len(line1) != len(line2):
                        return False
                    for i, answer in enumerate(line1):
                        if answer.strip() != line2[i].strip():
                            return False
        except Exception:
            return False
        return True

    def special_judge(self, case_id):
        spj_cpu_time = 20000  # 10s
        spj_real_time = 60000  # 30s
        spj_memory = 256 * 1024 * 1024  # 256M
        input_path = case_id + ".out"
        output_path = case_id + ".spj"
        spj_path = os.path.join(self.data_dir, 'spj')
        run_command = spj_path
        if not os.path.exists(spj_path):
            spj_path += '.py'
            run_command = '/usr/bin/python3 ' + spj_path
        if not os.path.exists(spj_path):
            raise JudgeServiceError("no spj found")
        run_command = run_command.split(' ')
        exe_path = run_command[0]
        args = run_command[1:]
        run_result = _judger.run(max_cpu_time=spj_cpu_time,
                                 max_real_time=spj_real_time,
                                 max_memory=spj_memory,
                                 max_stack=256 * 1024 * 1024,
                                 max_output_size=self._max_output_size,
                                 max_process_number=-1,
                                 exe_path=exe_path,
                                 input_path=input_path,
                                 output_path=output_path,
                                 error_path=output_path,
                                 args=args,
                                 env=default_env,
                                 log_path="spj.log",
                                 uid=0,
                                 gid=0,
                                 seccomp_rule_name='',
                                 memory_limit_check_only=0,
                                 )
        if run_result['result'] != _judger.RESULT_SUCCESS:
            return False
        if not os.path.exists(output_path):
            return False
        try:
            with open(output_path) as f:
                for line in f.readlines():
                    if not line:
                        continue
                    if line == '':
                        continue
                    try:
                        if int(line) == 0:
                            return True
                    except ValueError:
                        pass

        except Exception:
            pass
        return False
