import io
import sys
import threading
import time
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, Mock, patch

import numpy as np
from core import audio_devices as audio


class AudioRoutingTests(unittest.TestCase):
    def setUp(self):
        for name, value in (('_cache', None), ('_probe_results', {}),
                            ('_chosen_api', {'input': None, 'output': None}),
                            ('_RATES', {'input': 16000, 'output': 24000})):
            p = patch.object(audio, name, value)
            p.start(); self.addCleanup(p.stop)
        rows = [
            ('Mapeador de som da Microsoft - Input', 0, 2, 0),
            ('Microfone (Realtek High Definit', 0, 2, 0),
            ('Mapeador de som da Microsoft - Output', 0, 0, 2),
            ('Alto-falantes (Realtek High Def', 0, 0, 2),
            ('Driver de captura de som primário', 1, 2, 0),
            ('Microfone (Realtek High Definition Audio)', 1, 2, 0),
            ('Driver de som primário', 1, 0, 2),
            ('Alto-falantes (Realtek High Definition Audio)', 1, 0, 2),
            ('Alto-falantes (Realtek High Definition Audio)', 2, 0, 2),
            ('Microfone (Realtek High Definition Audio)', 2, 2, 0),
            ('USB Headphones', 0, 0, 2),
        ]
        self.devices = [dict(name=n, hostapi=a, max_input_channels=i, max_output_channels=o) for n, a, i, o in rows]
        self.sd = NS(query_devices=Mock(return_value=self.devices),
                     query_hostapis=Mock(return_value=[{'name': n} for n in ('MME', 'Windows DirectSound', 'Windows WASAPI')]),
                     default=NS(device=[1, 3]))
        p = patch.dict(sys.modules, {'sounddevice': self.sd})
        p.start(); self.addCleanup(p.stop)
        p = patch('platform.system', return_value='Windows')
        p.start(); self.addCleanup(p.stop)
        self.output = io.StringIO()
        p = redirect_stdout(self.output)
        p.__enter__(); self.addCleanup(p.__exit__, None, None, None)

    def routing(self):
        usable = patch.object(audio, '_usable', return_value=True)
        transport = patch.object(audio, '_transport_works', side_effect=lambda idx, kind, key: idx not in (7, 8))
        usable.start(); self.addCleanup(usable.stop)
        result = transport.start(); self.addCleanup(transport.stop)
        return result

    def test_portuguese_and_english_aliases_are_excluded(self):
        for name in ('Mapeador de som da Microsoft - Output', 'Driver de som primário',
                     'Driver de captura de som primário', 'Primary Sound Driver', 'Microsoft Sound Mapper'):
            self.assertTrue(audio._is_pseudo(name))
        self.assertFalse(audio._is_pseudo('Alto-falantes (Realtek High Definition Audio)'))

    def test_default_is_a_verified_physical_id_on_each_direction(self):
        transport = self.routing()
        self.assertEqual(audio.resolve('', 'input'), 5)
        self.assertEqual(audio.resolve('', 'output'), 3)
        self.assertEqual(len(audio.list_devices('input')), 1)
        self.assertEqual(len(audio.list_devices('output')), 2)
        self.assertEqual(audio._chosen_api, {'input': 'directsound', 'output': 'mme'})
        self.assertFalse(any(audio._is_pseudo(n) for n in audio.list_devices('output')))
        self.assertTrue(any(call.args[0] == 3 for call in transport.call_args_list))

    def test_named_resolution_rejects_silent_api_and_matches_truncated_names(self):
        self.routing()
        self.assertEqual(audio.resolve('Alto-falantes (Realtek High Definition Audio)', 'output'), 3)

    def test_respects_physical_os_default_instead_of_first_listed(self):
        self.routing()
        self.sd.default.device = [1, 10]
        self.assertEqual(audio.resolve('', 'output'), 10)

    def test_removed_or_failed_endpoint_uses_verified_fallback(self):
        self.routing()
        self.assertEqual(audio.resolve('Unplugged headset', 'output'), 3)
        self.assertEqual(audio.resolve('', 'output', exclude=(3,)), 10)

    def test_no_transport_is_an_error_not_silent_device_none(self):
        self.routing()
        with patch.object(audio, '_transport_works', return_value=False):
            with self.assertRaises(audio.AudioDeviceUnavailable): audio.resolve('', 'output')

    def test_configuration_invalidates_only_when_rates_change(self):
        audio._cache = {'input': ['mic'], 'output': ['spk']}
        audio._probe_results['old'] = True
        audio.configure(16000, 24000)
        self.assertIsNotNone(audio._cache)
        audio.configure(48000, 48000)
        self.assertIsNone(audio._cache)
        self.assertEqual(audio._probe_results, {})

    def test_concurrent_enumerations_are_coalesced(self):
        calls = []
        def query():
            calls.append(1)
            time.sleep(.02)
            return {'input': ['mic'], 'output': ['spk']}
        with patch.object(audio, '_query', side_effect=query):
            workers = [threading.Thread(target=audio.list_devices, args=(kind,)) for kind in ('input', 'output')]
            for worker in workers: worker.start()
            for worker in workers: worker.join(1)
        self.assertEqual(len(calls), 1)

    def test_probe_is_per_endpoint_and_closes_on_failure(self):
        streams = [Mock(), Mock()]
        self.sd.RawOutputStream = Mock(side_effect=streams)
        streams[1].write.side_effect = RuntimeError('Driver failed')
        with patch.object(audio.time, 'monotonic', side_effect=[0, .7, 1]):
            self.assertTrue(audio._transport_works(3, 'output', 'same-api'))
            self.assertFalse(audio._transport_works(10, 'output', 'same-api'))
        for stream in streams: stream.close.assert_called_once()
        self.assertEqual(self.sd.RawOutputStream.call_count, 2)

    def test_cleanup_closes_even_if_stop_raises(self):
        stream = Mock()
        stream.stop.side_effect = RuntimeError()
        audio._close_stream(stream)
        stream.close.assert_called_once()

    def test_output_close_waits_for_pending_write(self):
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        stream = Mock()
        def write(data):
            entered.set()
            release.wait(1)
        stream.write.side_effect = write
        stream.close.side_effect = closed.set
        output = audio.SerializedOutput(stream)
        writer = threading.Thread(target=output.write, args=(b'audio',))
        writer.start()
        self.assertTrue(entered.wait(.5))
        closer = threading.Thread(target=output.close)
        closer.start()
        self.assertFalse(closed.wait(.02))
        release.set()
        writer.join(1); closer.join(1)
        self.assertTrue(closed.is_set())
        with self.assertRaises(RuntimeError): output.write(b'late')

    def test_input_peak_handles_negative_full_scale_without_overflow(self):
        stream = MagicMock()
        def create(**kwargs):
            stream.__enter__.side_effect = lambda: kwargs['callback'](np.array([-32768], dtype=np.int16).tobytes(), 1, None, None)
            return stream
        self.sd.RawInputStream = create
        with patch.object(audio, 'resolve', return_value=5), patch.object(audio.time, 'sleep'):
            result = audio.measure_input('', .5)
        self.assertEqual(result['peak'], 32768)
        self.assertNotIn('clareza', result['verdict'])

    def test_tone_uses_real_stream_contract_and_does_not_claim_human_hearing(self):
        stream = Mock()
        self.sd.RawOutputStream = Mock(return_value=stream)
        self.sd.play = Mock()
        with patch.object(audio, 'resolve', return_value=3):
            result = audio.play_tone('', .6)
        self.assertTrue(result['ok'])
        self.assertFalse(result['heard_verified'])
        self.assertEqual(self.sd.RawOutputStream.call_args.kwargs['device'], 3)
        self.assertEqual(len(stream.write.call_args.args[0]), 28800)
        self.sd.play.assert_not_called()
        stream.close.assert_called_once()

    def test_diagnostics_do_not_raise_if_no_device_can_be_opened(self):
        with patch.object(audio, 'resolve', side_effect=audio.AudioDeviceUnavailable('No device')):
            self.assertFalse(audio.measure_input('')['ok'])
            self.assertFalse(audio.play_tone('')['ok'])

    def test_named_volume_unmutes_and_checks_readback(self):
        endpoint = Mock()
        endpoint.GetMute.side_effect = [True, False]
        endpoint.GetMasterVolumeLevelScalar.return_value = .4
        with patch.object(audio, '_endpoint_for', return_value=endpoint):
            self.assertTrue(audio.set_output_volume(40, 'speaker'))
        endpoint.SetMute.assert_called_once_with(0, None)


if __name__ == '__main__': unittest.main()
