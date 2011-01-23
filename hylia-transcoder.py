#!/usr/bin/env python
# encoding: utf-8

import sys, os, time, thread
import glib, gobject, pygst
import argparse
pygst.require('0.10')
import gst


loop = glib.MainLoop()


class Main(object):
	def __init__(self):
		self.transcoder = gst.Pipeline('transcoder')
		
		self.input_file = gst.element_factory_make('filesrc', 'input-file')
		self.decoder = gst.element_factory_make('decodebin2', 'decoder')
		self.decoder.connect('pad-added', self.decoder_pad_added)
		
		queues = []
		
		self.video_input_queue = gst.element_factory_make('queue2', 'video-input-queue')
		queues.append(self.video_input_queue)
		self.video_encoder = gst.element_factory_make('x264enc', 'video-encoder')
		self.video_encoder.set_property('speed-preset', 1)
		self.video_encoder.set_property('tune', 0x00000004)
		#self.video_encoder.set_property('bitrate', 2048)
		
		h264parse = gst.element_factory_make('h264parse', 'h264parse')
		h264parse.set_property('output-format', 1)
		self.video_output_queue = gst.element_factory_make('queue2', 'video-output-queue')
		queues.append(self.video_output_queue)
		
		self.audio_input_queue = gst.element_factory_make('queue2', 'audio-input-queue')
		queues.append(self.audio_input_queue)
		audioconvert = gst.element_factory_make('audioconvert', 'audioconvert')
		self.audio_encoder = gst.element_factory_make('ffenc_mp2', 'audio-encoder')
		self.audio_output_queue = gst.element_factory_make('queue2', 'audio-output-queue')
		queues.append(self.audio_output_queue)
		
		self.muxer = gst.element_factory_make('ffmux_mpegts', 'muxer')
		self.output_file = gst.element_factory_make('filesink', 'output-file')
		
		self.transcoder.add(
			self.input_file,
			self.decoder,
			self.video_input_queue,
			self.video_encoder,
			h264parse,
			self.video_output_queue,
			self.audio_input_queue,
			audioconvert,
			self.audio_encoder,
			self.audio_output_queue,
			self.muxer,
			self.output_file
		)
		
		for queue in queues:
			queue.set_property('max-size-buffers', 0)
			queue.set_property('max-size-bytes', 0)
			queue.set_property('max-size-time', 0)
		
		gst.element_link_many(
			self.input_file,
			self.decoder
		)
		
		gst.element_link_many(
			self.video_input_queue,
			self.video_encoder,
			h264parse,
			self.video_output_queue,
			self.muxer
		)
		
		gst.element_link_many(
			self.audio_input_queue,
			audioconvert,
			self.audio_encoder,
			self.audio_output_queue,
			self.muxer
		)
		
		gst.element_link_many(
			self.muxer,
			self.output_file
		)
		
		bus = self.transcoder.get_bus()
		bus.add_signal_watch()
		bus.connect('message', self.on_message)
	
	def decoder_pad_added(self, decoder, pad):
		print pad.get_caps()
		if pad.get_caps().to_string()[0:5] == 'video':
			pad.link(self.video_input_queue.get_pad('sink'))
		elif pad.get_caps().to_string()[0:5] == 'audio':
			pad.link(self.audio_input_queue.get_pad('sink'))
	
	def on_message(self, bus, message):
		t = message.type
		if t == gst.MESSAGE_EOS:
			self.transcoder.set_state(gst.STATE_NULL)
			self.playmode = False
		elif t == gst.MESSAGE_ERROR:
			self.transcoder.set_state(gst.STATE_NULL)
			err, debug = message.parse_error()
			print "Error: %s" % err, debug
			self.playmode = False
	
	def start(self, args):
		if os.path.isfile(args.input):
			self.playmode = True
			self.transcoder.get_by_name('input-file').set_property('location', args.input)
			self.transcoder.get_by_name('output-file').set_property('location', args.output)
			self.transcoder.set_state(gst.STATE_PLAYING)
			while self.playmode:
				time.sleep(1)
		
		time.sleep(1)
		loop.quit()


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Hylia intelligent media transcoder.')
	parser.add_argument('input', help='the path or URL of media to be transcoded')
	parser.add_argument('output', help='the path where transcoded data will be sent (defaults to /dev/null for testing)', nargs='?', default='/dev/null')
	args = parser.parse_args()
	
	print args
	
	mainclass = Main()
	thread.start_new_thread(mainclass.start, (args,))
	gobject.threads_init()
	loop.run()