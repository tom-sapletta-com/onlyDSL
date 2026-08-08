# -*- coding: utf-8 -*-
# Generated for the POC from contracts/ifuri/v1/envelope.proto. DO NOT EDIT BY HAND.
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
from google.protobuf import any_pb2 as google_dot_protobuf_dot_any__pb2
from google.protobuf import timestamp_pb2 as google_dot_protobuf_dot_timestamp__pb2
_sym_db = _symbol_database.Default()
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x17ifuri/v1/envelope.proto\x12\x08ifuri.v1\x1a\x19google/protobuf/any.proto\x1a\x1fgoogle/protobuf/timestamp.proto"\x98\x03\n\x08Envelope\x12\x18\n\x10envelope_version\x18\x01 \x01(\r\x12\n\n\x02id\x18\x02 \x01(\t\x12\x12\n\ntarget_uri\x18\x03 \x01(\t\x12\x12\n\nsource_uri\x18\x04 \x01(\t\x12#\n\x04kind\x18\x05 \x01(\x0e2\x15.ifuri.v1.MessageKind\x12%\n\x07payload\x18\x06 \x01(\x0b2\x14.google.protobuf.Any\x12.\n\ncreated_at\x18\x07 \x01(\x0b2\x1a.google.protobuf.Timestamp\x12\x16\n\x0ecorrelation_id\x18\x08 \x01(\t\x12\x14\n\x0ccausation_id\x18\t \x01(\t\x12\x14\n\x0caggregate_id\x18\n \x01(\t\x12\x19\n\x11aggregate_version\x18\x0b \x01(\x04\x122\n\x08metadata\x18\x0c \x03(\x0b2 .ifuri.v1.Envelope.MetadataEntry\x1a/\n\rMetadataEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x028\x01*Y\n\x0bMessageKind\x12\x1c\n\x18MESSAGE_KIND_UNSPECIFIED\x10\x00\x12\x0b\n\x07COMMAND\x10\x01\x12\t\n\x05QUERY\x10\x02\x12\t\n\x05EVENT\x10\x03\x12\t\n\x05REPLY\x10\x04b\x06proto3')
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'ifuri_core.envelope_pb2', globals())
