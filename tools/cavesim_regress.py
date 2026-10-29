#!/usr/bin/env python3
"""cavesim_regress: the byte-identical regression battery for tools/cavesim.py.

The rule when cavesim grows (offline workflow B2, 2026-10-10): the probe90 control
(`python tools/cavesim.py probe90` -> AL = 0x0E) and every probe172..178 run must print
EXACTLY the same bytes after the change as before it. This runs the battery and either
records the output (`--record`, do this ONLY from a cavesim you trust, e.g. `git stash`ed
to HEAD) or diffs against the recorded copy.

    python tools/cavesim_regress.py --record     # write build/analysis/cavesim-golden/*.txt
    python tools/cavesim_regress.py              # run again and diff; exit 1 on any difference
    python tools/cavesim_regress.py --list       # print the battery

The golden files were recorded from the cavesim of commit 34d9c45 (before B2).

J-T3 (2026-10-12) adds a SECOND battery after the first: the EXTENSION cases, one golden each
(build/analysis/cavesim-golden/ext_*.txt), for the failure-world options (--cancel,
--ksink-after-unload, --wrong-dsp, --mid-chunk-1072, --foreign-tone, --mem-at), the sinkState
guard mock and the cave-carried trap stub (T12). The first battery and its "169 cases: 169
identical" line are untouched and its goldens are never rewritten by the new code:

    python tools/cavesim_regress.py --record-new  # write ONLY the ext goldens that are missing
    python tools/cavesim_regress.py               # run both batteries, exit 1 on any difference

(`--record` still rewrites the FIRST battery only; do not use it casually.) Mock caves are built
in a temp dir by tools/cavesim_selftest.py's builders and the temp path is normalised to <tmp>.

Round 3 (2026-10-12, T14) appends 12 cases to the extension battery (a cave branch into the trap tail,
an unimplemented-slot stub, the R05 consume lever with and without --caller-frame, the census mock under
--size-dries-after / --src-unpacked). The goldens of the 33 older ext cases are untouched EXCEPT
ext_synth_stray, whose behaviour changed on purpose: xapemu no longer runs a stray 0x0E as a pseudo-TRAP,
so the run now STOPS (T14 section 3); its old golden is kept beside it as ext_synth_stray.round2.txt.
"""
import difflib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(ROOT, 'build', 'analysis', 'cavesim-golden')
E = ['--entry', '0x3E21D']
HOOK = E + ['--al', '4004']

CASES = {'probe90_control': ['probe90']}
for p in range(172, 179):
    n = 'probe%d' % p
    CASES[n + '_busy'] = [n] + HOOK
    CASES[n + '_start'] = [n] + HOOK + ['--fail', 'TransformFromSink']
    CASES[n + '_replay4003'] = [n] + E + ['--al', '4003']
    CASES[n + '_replay0'] = [n] + E + ['--al', '0']
    CASES[n + '_dsp_up'] = [n] + HOOK + ['--fail', 'TransformFromSink', '--dsp', 'up', '--events', '8']
    CASES[n + '_dsp_down'] = [n] + HOOK + ['--fail', 'TransformFromSink', '--dsp', 'down']
    CASES[n + '_teardown'] = [n] + HOOK + ['--fail', 'TransformFromSink', '--dsp', 'up',
                                           '--teardown', '--events', '6']
    CASES[n + '_busy_dsp'] = [n] + HOOK + ['--dsp', 'up', '--events', '6']
    for f in ('StreamKalimbaSink', 'FileFind', 'StreamFileSource', 'TransformAdpcmDecode',
              'TransformStart', 'KalimbaSendMessage', 'StreamDisconnect', 'TransformStop',
              'TransformDisconnect'):
        CASES[n + '_fail_' + f] = [n] + HOOK + ['--fail', 'TransformFromSink', '--fail', f]
    for f, k in (('TransformAdpcmDecode', 2), ('TransformStart', 2), ('StreamFileSource', 2),
                 ('FileFind', 3), ('FileFind', 4), ('StreamKalimbaSink', 2)):
        CASES['%s_failafter_%s%d' % (n, f, k)] = (
            [n] + HOOK + ['--fail', 'TransformFromSink', '--dsp', 'up', '--events', '8',
                          '--fail-after', '%s=%d' % (f, k)])
CASES['probe172_dump'] = ['probe172'] + HOOK + ['--dump']
# a few older caves that exercise the modelled partition / DSP / gather paths
CASES['probe139_pmap'] = ['probe139', '--pmap', '{"0":1,"2":0}']
CASES['probe140'] = ['probe140']
CASES['probe160_dsp'] = ['probe160', '--dsp', 'up', '--teardown']
CASES['probe161_dsp'] = ['probe161', '--dsp', 'up', '--teardown']
CASES['probe165_dsp'] = ['probe165', '--dsp', 'up', '--events', '12']
CASES['probe168_dsp'] = ['probe168', '--dsp', 'up', '--events', '12']


def run(args, norm=None):
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'cavesim.py')] + args,
                       capture_output=True, text=True, cwd=ROOT, timeout=300)
    out = 'argv: %s\nexit: %d\n--stdout--\n%s--stderr--\n%s' % (
        ' '.join(args), r.returncode, r.stdout, r.stderr)
    for n in (norm or []):
        out = out.replace(n, '<tmp>').replace(n.replace('\\', '/'), '<tmp>')
    return out


# ---- J-T3 extension battery ------------------------------------------------------------------
S181 = ['probe181'] + E + ['--al', '4004', '--press', '0:4004', '--brief']
EXT = {
    'ext_181_cancel_never_gap': S181 + ['--press', '2800:4004', '--horizon', '30000',
                                         '--cancel', 'never'],
    'ext_181_cancel_never_body': S181 + ['--press', '1500:4004', '--horizon', '30000',
                                          '--cancel', 'never'],
    'ext_181_cancel_always': S181 + ['--press', '2800:4004', '--cancel', 'always'],
    'ext_181_paused': S181 + ['--music', 'paused', '--unload-ms', '100', '--horizon', '20000'],
    'ext_181_paused_ksink_zero': S181 + ['--music', 'paused', '--unload-ms', '100',
                                          '--horizon', '20000', '--ksink-after-unload', 'zero'],
    'ext_181_wrong_dsp': S181 + ['--wrong-dsp', '4000:3000', '--horizon', '14000'],
    'ext_181_mid1072_b0': S181 + ['--mid-chunk-1072', '4000:0', '--horizon', '9000'],
    'ext_181_mid1072_b2': S181 + ['--mid-chunk-1072', '4000:2', '--horizon', '9000'],
    'ext_181_mid1072_latch_immediate': ['probe181'] + E + ['--al', '4004', '--press', '0:4004',
                                         '--brief', '--mid-chunk-1072', '4000:0', '--latch',
                                         'immediate', '--stock-rate', '2000', '--horizon', '9000'],
    'ext_181_foreign_tone': S181 + ['--foreign-tone', '4000:2000', '--horizon', '9000'],
    'ext_181_mem59e_6_hole': ['probe181'] + E + ['--al', '4004', '--press', '0:4004', '--brief',
                                                  '--loop', '3', '--mem', '59e=6'],
    'ext_181_mem59e_0_hole': ['probe181'] + E + ['--al', '4004', '--press', '0:4004', '--brief',
                                                  '--loop', '3', '--mem', '59e=0'],
    'ext_181_E5_wrongdsp_call': S181 + ['--mem', '59e=d', '--mem-at', '3500:59e=6',
                                        '--wrong-dsp', '3500:3000', '--horizon', '14000'],
    'ext_180_cancel_never': ['probe180'] + E + ['--al', '4004', '--press', '0:4004', '--brief',
                                                 '--press', '4500:4004', '--horizon', '30000',
                                                 '--cancel', 'never'],
    'ext_179_wrong_dsp': ['probe179'] + E + ['--al', '4004', '--loop', '3', '--brief',
                                              '--wrong-dsp', '2500:3000', '--settle-ms', '8000'],
    'ext_178_mid1072_b0': ['probe178'] + E + ['--al', '4004', '--loop', '3', '--press-gap', '5000',
                                               '--brief', '--mid-chunk-1072', '9000:0'],
    'ext_guard_s0': ['mock:guard'] + E + ['--al', '4004', '--press', '0:4004', '--brief', '--loop',
                                           '3', '--mem', '59e=0'],
    'ext_guard_s3': ['mock:guard'] + E + ['--al', '4004', '--press', '0:4004', '--brief', '--loop',
                                           '3', '--mem', '59e=3'],
    'ext_guard_s6': ['mock:guard'] + E + ['--al', '4004', '--press', '0:4004', '--brief', '--loop',
                                           '3', '--mem', '59e=6'],
    'ext_guard_s13': ['mock:guard'] + E + ['--al', '4004', '--press', '0:4004', '--brief', '--loop',
                                            '3', '--mem', '59e=d'],
    'ext_guard_E5': ['mock:guard'] + E + ['--al', '4004', '--press', '0:4004', '--brief', '--mem',
                                           '59e=d', '--mem-at', '3500:59e=6', '--wrong-dsp',
                                           '3500:3000', '--horizon', '14000'],
    'ext_181_voicefield_short_converted': S181 + ['--press', '5000:4045', '--voice-field',
                                                  '--horizon', '20000'],
    'ext_181_voicefield_off_short_replayed': S181 + ['--press', '5000:4045', '--horizon', '20000'],
    'ext_181_voicefield_hfp_clears': S181 + ['--press', '5000:4045', '--voice-field',
                                             '--field-at', '2000:0', '--horizon', '20000'],
    'ext_181_voicefield_parity': ['probe181'] + E + ['--al', '4004', '--press', '0:4004',
                                                      '--press', '20000:4004', '--press',
                                                      '40000:4004', '--brief', '--voice-field',
                                                      '--horizon', '60000'],
    'ext_gain_nopreset': ['mock:gain'] + E,
    'ext_gain_preset': ['mock:gain'] + E + ['--mem', '6d0=3100'],
    'ext_gain_group2': ['mock:gain_g2'] + E + ['--mem', '6d0=3100'],
    'ext_synth_d3': ['mock:synth_ok'] + E,
    'ext_synth_d3_fail': ['mock:synth_ok'] + E + ['--fail', 'PartitionGetRawSerialSource'],
    'ext_synth_d3_below': ['mock:synth_below', '--entry', '0x3E240'],
    'ext_synth_d3_world': ['mock:synth_ok'] + E + ['--world', '--once', '--brief'],
    'ext_synth_stray': ['mock:synth_stray'] + E,
    # ---- round 3 (T14)
    'ext_synth_bsr_tail': ['mock:synth_bsrtail'] + E,
    'ext_synth_bra_tail': ['mock:synth_bratail'] + E,
    'ext_synth_unimpl': ['mock:synth_unimpl'] + E,
    'ext_synth_near_cell': ['mock:synth_near_cell'] + E,
    'ext_consume_4004': ['mock:consume'] + E + ['--al', '4004'] + ['--frame', '13=1', '--frame', '14=0', '--show', '90D:2'],
    'ext_consume_4045': ['mock:consume'] + E + ['--frame', '13=1', '--frame', '14=0', '--show', '90D:2',
                                                 '--al', '4045'],
    'ext_consume_callerframe': ['mock:consume'] + E + ['--al', '4004'] + ['--frame', '13=1', '--frame', '14=0', '--show',
                                                        '90D:2', '--caller-frame', '23'],
    'ext_consume_bad_callerframe': ['mock:consume_bad'] + E + ['--al', '4004'] + ['--frame', '13=1', '--frame', '14=0',
                                                                '--show', '90D:2', '--caller-frame',
                                                                '23'],
    'ext_consume_bad_nocheck': ['mock:consume_bad'] + E + ['--al', '4004'] + ['--frame', '13=1', '--frame', '14=0',
                                                            '--show', '90D:2'],
    'ext_census_dries': ['mock:census'] + E + ['--world', '--once', '--size-dries-after', '1'],
    'ext_census_unpacked': ['mock:census'] + E + ['--world', '--once', '--src-unpacked'],
    'ext_census_packed': ['mock:census'] + E + ['--world', '--once'],
}

def build_mocks(tmp):
    """Mock caves for the extension battery -> {'mock:name': path}."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import cavesim_selftest as st
    out = {}
    out['mock:guard'] = os.path.join(tmp, 'mock_guard_words.json')
    st.build('guard', out['mock:guard'])
    out['mock:gain'] = os.path.join(tmp, 'mock_gain_words.json')
    st.build_gain(out['mock:gain'])
    out['mock:gain_g2'] = os.path.join(tmp, 'mock_gain_g2_words.json')
    st.build_gain(out['mock:gain_g2'], group=2)
    for key, mode in (('synth_ok', 'ok'), ('synth_below', 'below'), ('synth_stray', 'stray'),
                      ('synth_bsrtail', 'bsrtail'), ('synth_bratail', 'bratail'),
                      ('synth_near_cell', 'near_cell')):
        out['mock:' + key] = os.path.join(tmp, 'mock_%s_words.json' % key)
        st.build_synth(out['mock:' + key], 0xD3, mode)
    out['mock:synth_unimpl'] = os.path.join(tmp, 'mock_synth_unimpl_words.json')
    st.build_synth(out['mock:synth_unimpl'], 0xDA, 'ok')
    for key, slots in (('consume', (21, 22)), ('consume_bad', (29, 30))):
        out['mock:' + key] = os.path.join(tmp, 'mock_%s_words.json' % key)
        st.build_consume(out['mock:' + key], slots)
    out['mock:census'] = os.path.join(tmp, 'mock_census_words.json')
    st.build('census', out['mock:census'])
    return out


def run_ext(record_new):
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix='cavesim_regress_')
    bad = missing = new = 0
    try:
        mocks = build_mocks(tmp)
        for n, a in EXT.items():
            args = [mocks.get(a[0], a[0])] + a[1:]
            out = run(args, norm=[tmp])
            path = os.path.join(GOLD, n + '.txt')
            if not os.path.exists(path):
                if record_new:
                    with open(path, 'w', newline='\n') as f:
                        f.write(out)
                    new += 1
                else:
                    print('MISSING golden: %s' % n)
                    missing += 1
                continue
            with open(path, newline='\n') as f:
                gold = f.read()
            if gold != out:
                bad += 1
                print('DIFFERS: %s' % n)
                for line in list(difflib.unified_diff(gold.splitlines(), out.splitlines(),
                                                      'golden', 'now', lineterm='', n=1))[:40]:
                    print('  ' + line)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if record_new:
        print('recorded %d new extension goldens (existing ones untouched)' % new)
    print('%d extension cases: %d identical, %d differ, %d missing golden'
          % (len(EXT), len(EXT) - bad - missing, bad, missing))
    return bad, missing


def main():
    if '--list' in sys.argv:
        for n, a in CASES.items():
            print('%-40s %s' % (n, ' '.join(a)))
        for n, a in EXT.items():
            print('%-40s %s' % (n, ' '.join(a)))
        return 0
    if '--record-new' in sys.argv:
        os.makedirs(GOLD, exist_ok=True)
        run_ext(True)
        return 0
    record = '--record' in sys.argv
    os.makedirs(GOLD, exist_ok=True)
    bad = missing = 0
    for n, a in CASES.items():
        out = run(a)
        path = os.path.join(GOLD, n + '.txt')
        if record:
            with open(path, 'w', newline='\n') as f:
                f.write(out)
            continue
        if not os.path.exists(path):
            print('MISSING golden: %s' % n)
            missing += 1
            continue
        with open(path, newline='\n') as f:
            gold = f.read()
        if gold != out:
            bad += 1
            print('DIFFERS: %s' % n)
            for line in list(difflib.unified_diff(gold.splitlines(), out.splitlines(),
                                                  'golden', 'now', lineterm='', n=1))[:40]:
                print('  ' + line)
    if record:
        print('recorded %d cases to %s' % (len(CASES), os.path.relpath(GOLD, ROOT)))
        return 0
    print('%d cases: %d identical, %d differ, %d missing golden'
          % (len(CASES), len(CASES) - bad - missing, bad, missing))
    ebad, emissing = run_ext(False)
    return 1 if bad or missing or ebad or emissing else 0


if __name__ == '__main__':
    sys.exit(main())
