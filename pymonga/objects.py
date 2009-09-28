# coding: utf-8
# Copyright 2009 Alexandre Fiori
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import types
from pymonga._pymongo.son import SON
from pymonga._pymongo.objectid import ObjectId
from pymonga import filter as qf
from twisted.internet.defer import Deferred

"""Utilities for dealing with Mongo objects: Database and Collection"""

class Database(object):
    def __init__(self, tracker, database_name):
        self._tracker = tracker
        self._database_name = database_name

    @property
    def _connection(self):
        return self._tracker()

    def __str__(self):
        return self._database_name

    def __repr__(self):
        return "<mongodb Database: %s>" % self._database_name

    def __getitem__(self, collection_name):
        return Collection(self, collection_name)

    def __getattr__(self, collection_name):
        return Collection(self, collection_name)


class Collection(object):
    def __init__(self, database, collection_name):
        self._database = database
        self._collection_name = collection_name

    def __str__(self):
        return "%s.%s" % (str(self._database), self._collection_name)

    def __repr__(self):
        return "<mongodb Collection: %s.%s>" % str(self)

    def _fields_list_to_dict(self, fields):
        """
        transform a list of fields from ["a", "b"] to {"a":1, "b":1}
        """
        as_dict = {}
        for field in fields:
            if not isinstance(field, types.StringType):
                raise TypeError("fields must be a list of key names")
            as_dict[field] = 1
        return as_dict

    def _safe_operation(self, proto, safe=False):
        if safe is True:
            deferred = self._database["$cmd"].find_one({"getlasterror":1}, _proto=proto)
        else:
            deferred = Deferred()
            deferred.callback(None)
        return deferred

    def find(self, spec=None, skip=0, limit=0, fields=None, filter=None, _proto=None):
        if spec is None: spec = SON()

        if not isinstance(spec, types.DictType):
            raise TypeError("spec must be an instance of dict")
        if not isinstance(fields, (types.ListType, types.NoneType)):
            raise TypeError("fields must be an istance of list")
        if not isinstance(skip, types.IntType):
            raise TypeError("skip must be an instance of int")
        if not isinstance(limit, types.IntType):
            raise TypeError("limit must be an instance of int")

        if fields is not None:
            if not fields:
                fields = ["_id"]
            fields = self._fields_list_to_dict(fields)

        if isinstance(filter, (qf.sort, qf.hint, qf.explain, qf.snapshot)):
            spec = SON(dict(query=spec))
            for k, v in filter.items():
                spec[k] = isinstance(v, types.TupleType) and SON(v) or v

        # send the command through a specific connection
        # this is required for the connection pool to work
        # when safe=True
        if _proto is None:
            proto = self._database._connection
        else:
            proto = _proto
        return proto._OP_QUERY(str(self), spec, skip, limit, fields)

    def find_one(self, spec=None, fields=None, _proto=None):
        def wrapper(docs):
            return docs and docs[0] or {}

        if isinstance(spec, ObjectId):
            spec = SON(dict(_id=spec))

        d = self.find(spec, limit=-1, fields=fields, _proto=_proto)
        d.addCallback(wrapper)
        return d

    def count(self, spec=None, fields=None):
        def wrapper(result):
            return result["n"]

        if fields is not None:
            if not fields:
                fields = ["_id"]
            fields = self._fields_list_to_dict(fields)

        spec = SON([("count", self._collection_name),
                    ("query", spec or SON()),
                    ("fields", fields)])
        d = self._database["$cmd"].find_one(spec)
        d.addCallback(wrapper)
        return d

    def insert(self, docs, safe=False):
        if isinstance(docs, types.DictType):
            docs = [docs]
        if not isinstance(docs, types.ListType):
            raise TypeError("insert takes a document or a list of documents")
        proto = self._database._connection
        proto._OP_INSERT(str(self), docs)
        return self._safe_operation(proto, safe)

    def update(self, spec, document, upsert=False, safe=False):
        if not isinstance(spec, types.DictType):
            raise TypeError("spec must be an instance of dict")
        if not isinstance(document, types.DictType):
            raise TypeError("document must be an instance of dict")
        if not isinstance(upsert, types.BooleanType):
            raise TypeError("upsert must be an instance of bool")
        proto = self._database._connection
        proto._OP_UPDATE(str(self), spec, document)
        return self._safe_operation(proto, safe)
    
    def remove(self, spec, safe=False):
        if isinstance(spec, ObjectId):
            spec = SON(dict(_id=spec))
        if not isinstance(spec, types.DictType):
            raise TypeError("spec must be an instance of dict, not %s" % type(spec))
        proto = self._database._connection
        proto._OP_DELETE(str(self), spec)
        return self._safe_operation(proto, safe)

    def drop(self, safe=False):
        return self.remove({}, safe)
