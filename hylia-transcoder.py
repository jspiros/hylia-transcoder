#!/usr/bin/env python
# encoding: utf-8

# known issues:
# 	- gstreamer demuxes xvid as video/x-xvid, but mpegtsmuxer can only accept video/mpeg. capssetter doesn't fix this.
# 	- MPEG-4 video can't seem to be muxed in properly, anyway.
# 	- Doesn't seem to work with the PS3...

import sys, os, time, thread
import glib, gobject, pygst
import argparse
pygst.require('0.10')
import gst


loop = glib.MainLoop()


class Main(object):
	def __init__(self, parser, args):
		self.parser = parser
		self.args = args
		
		self.transcoder = gst.Pipeline('transcoder')
		
		self.input_file = gst.element_factory_make('filesrc', 'input-file')
		self.input_file.set_property('location', self.args.input)
		
		self.decoder = gst.element_factory_make('decodebin2', 'decoder')
		self.decoder.connect('autoplug-continue', self.decoder_autoplug_continue)
		self.decoder.connect('pad-added', self.decoder_pad_added)
		self.decoder.connect('no-more-pads', self.decoder_no_more_pads)
		
		queues = []
		
		self.video_input_queue = gst.element_factory_make('queue2', 'video-input-queue')
		queues.append(self.video_input_queue)
		self.video_output_queue = gst.element_factory_make('queue2', 'video-output-queue')
		queues.append(self.video_output_queue)
		
		self.audio_input_queue = gst.element_factory_make('queue2', 'audio-input-queue')
		queues.append(self.audio_input_queue)
		self.audio_output_queue = gst.element_factory_make('queue2', 'audio-output-queue')
		queues.append(self.audio_output_queue)
		
		self.muxer = gst.element_factory_make('mpegtsmux', 'muxer')
		self.output_file = gst.element_factory_make('filesink', 'output-file')
		self.output_file.set_property('location', self.args.output)
		
		self.transcoder.add(
			self.input_file,
			self.decoder,
			self.video_input_queue,
			self.video_output_queue,
			self.audio_input_queue,
			self.audio_output_queue,
			self.muxer,
			self.output_file
		)
		
		for queue in queues:
			queue.set_property('max-size-buffers', 0)
			queue.set_property('max-size-time', 0)
		
		gst.element_link_many(self.input_file, self.decoder)
		
		bus = self.transcoder.get_bus()
		bus.add_signal_watch()
		bus.connect('message', self.on_message)
	
	def decoder_autoplug_continue(self, decoder, pad, caps):
		caps_string = caps.to_string()
		if caps_string.startswith('video/x-h264'):
			return False
		elif caps_string.startswith('audio/x-ac3'):
			return False
		elif caps_string.startswith('audio/mpeg'): # could be AAC, MP3, MP2
			return False
		return True
	
	def decoder_pad_added(self, decoder, pad):
		caps_string = pad.get_caps().to_string()
		if caps_string.startswith('video'):
			pad.link(self.video_input_queue.get_pad('sink'))
			if caps_string.startswith('video/x-h264'):
				#h264parse = gst.element_factory_make('h264parse', 'h264parse')
				#h264parse.set_property('output-format', 1)
				#self.transcoder.add(h264parse)
				#gst.element_link_many(self.video_input_queue, h264parse, self.video_output_queue, self.muxer)
				gst.element_link_many(self.video_input_queue, self.video_output_queue, self.muxer)
				#h264parse.set_state(gst.STATE_PLAYING)
			else:
				video_encoder = gst.element_factory_make('ffenc_mpeg4', 'video-encoder')
				video_encoder.set_property('bitrate', (2048*1000))
				self.transcoder.add(video_encoder)
				gst.element_link_many(self.video_input_queue, video_encoder, self.video_output_queue, self.muxer)
				video_encoder.set_state(gst.STATE_PLAYING)
		elif caps_string.startswith('audio'):
			pad.link(self.audio_input_queue.get_pad('sink'))
			if caps_string.startswith('audio/x-ac3'):
				ac3parse = gst.element_factory_make('ac3parse', 'ac3parse')
				self.transcoder.add(ac3parse)
				gst.element_link_many(self.audio_input_queue, ac3parse, self.audio_output_queue, self.muxer)
				ac3parse.set_state(gst.STATE_PLAYING)
			elif caps_string.startswith('audio/mpeg'):
				gst.element_link_many(self.audio_input_queue, self.audio_output_queue, self.muxer)
			else:
				audioconvert = gst.element_factory_make('audioconvert', 'audioconvert')
				audio_encoder = gst.element_factory_make('ffenc_mp2', 'audio-encoder')
				self.transcoder.add(audioconvert, audio_encoder)
				gst.element_link_many(self.audio_input_queue, audioconvert, audio_encoder, self.audio_output_queue, self.muxer)
				audioconvert.set_state(gst.STATE_PLAYING)
				audio_encoder.set_state(gst.STATE_PLAYING)
	
	def decoder_no_more_pads(self, decoder):
		gst.element_link_many(self.muxer, self.output_file)
		self.transcoder.set_state(gst.STATE_PLAYING)
	
	def on_message(self, bus, message):
		t = message.type
		if t == gst.MESSAGE_EOS:
			self.transcoder.set_state(gst.STATE_NULL)
			self.playmode = False
		elif t == gst.MESSAGE_ERROR:
			self.transcoder.set_state(gst.STATE_NULL)
			err, debug = message.parse_error()
			logging.debug("Error: %s" % err, debug)
			self.playmode = False
	
	def start(self):
		self.playmode = True
		self.transcoder.set_state(gst.STATE_PAUSED)
		while self.playmode:
			time.sleep(1)
		
		time.sleep(1)
		loop.quit()


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Hylia intelligent media transcoder.')
	parser.add_argument('input', help='the path or URL of media to be transcoded')
	parser.add_argument('output', help='the path where transcoded data will be sent (defaults to /dev/null for testing)', nargs='?', default='/dev/null')
	args = parser.parse_args()
	if os.path.isfile(args.input):
		mainclass = Main(parser, args)
		thread.start_new_thread(mainclass.start, ())
		gobject.threads_init()
		loop.run()
	else:
		parser.error('Invalid input "%s"' % args.input)