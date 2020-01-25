import json
import pathlib
from typing import Dict, List

import _judger
import os
from exception import CompileError

default_env = ["LANG=en_US.UTF-8",
               "LANGUAGE=en_US:en",
               "LC_ALL=en_US.UTF-8",
               "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"]


class JudgerBridge:
    def __init__(self):
        self._max_output_size = 30 * 1024 * 1024
        self._max_process_number = 1
        self._uid = self._gid = 0
        self._env = default_env
        self._max_cpu_time = None
        self._max_real_time = None
        self._max_memory = None
        self._exe_path = None
        self._args = None
        self._seccomp_rule_name = None
        self._memory_limit_check_only = None


class Compiler(JudgerBridge):
    def __init__(self, command, base_dir):
        super().__init__()
        self._max_cpu_time = 5000
        self._max_real_time = 10000
        self._max_memory = 512 * 1024 * 1024  # 500MB
        self._memory_limit_check_only = 0
        self.command = command
        self.base_dir = base_dir

    def __call__(self) -> None:
        os.chdir(self.base_dir)
        compiler_out = "compiler.out"
        _command = self.command.split(" ")
        result = _judger.run(max_cpu_time=self._max_cpu_time,
                             max_real_time=self._max_real_time,
                             max_memory=self._max_memory,
                             max_stack=128 * 1024 * 1024,
                             max_output_size=1024 * 1024,
                             max_process_number=1,
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
                    # os.remove(compiler_out)
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
                 data_dir,submit_id,
                 spj):
        super().__init__()
        self.submit_id = submit_id
        self.judge_dir = judge_dir
        self.data_dir = data_dir
        self._max_cpu_time = max_cpu_time
        self._max_real_time = self._max_cpu_time * 2
        self._max_memory = max_memory
        command = command.split(' ')
        self._exe_path = command[0]
        self._args = command[1:]
        self._seccomp_rule_name = seccomp_rule
        self._memory_limit_check_only = memory_limit_check_only
        self.spj = spj

    def __call__(self) -> List[Dict]:
        os.chdir(self.judge_dir)
        datas = pathlib.Path(self.data_dir)
        results=[]
        for data in datas.glob("*.in"):
            case_id = data.stem
            output_path = case_id + ".out"
            err_path = case_id + ".err"
            input_path = str(data.absolute())
            run_result = _judger.run(max_cpu_time=self._max_cpu_time,
                                     max_real_time=self._max_real_time,
                                     max_memory=self._max_memory,
                                     max_stack=128 * 1024 * 1024,
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
        # TODO spj
        if self.spj:
            pass
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
