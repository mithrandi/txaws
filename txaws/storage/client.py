"""
Client wrapper for Amazon's Simple Storage Service.

API stability: unstable.

Various API-incompatible changes are planned in order to expose missing
functionality in this wrapper.
"""

from hashlib import md5
from base64 import b64encode

from epsilon.extime import Time

from twisted.web.client import getPage
from twisted.web.http import datetimeToString

from txaws.util import XML, calculate_md5
from txaws.service import AWSService


name_space = '{http://s3.amazonaws.com/doc/2006-03-01/}'


class S3Request(object):

    def __init__(self, verb, bucket=None, object_name=None, data='',
                 content_type=None,
        metadata={}, root_uri='https://s3.amazonaws.com',  service=None):
        self.verb = verb
        self.bucket = bucket
        self.object_name = object_name
        self.data = data
        self.content_type = content_type
        self.metadata = metadata
        self.root_uri = root_uri
        self.service = service
        self.date = datetimeToString()

    def get_uri_path(self):
        path = '/'
        if self.bucket is not None:
            path += self.bucket
            if self.object_name is not None:
                path += '/' + self.object_name
        return path

    def get_uri(self):
        return self.root_uri + self.get_uri_path()

    def get_headers(self):
        headers = {'Content-Length': len(self.data),
                   'Content-MD5': calculate_md5(self.data),
                   'Date': self.date}

        for key, value in self.metadata.iteritems():
            headers['x-amz-meta-' + key] = value

        if self.content_type is not None:
            headers['Content-Type'] = self.content_type

        if self.service is not None:
            signature = self.get_signature(headers)
            headers['Authorization'] = 'AWS %s:%s' % (
                self.service.access_key, signature)
        return headers

    def get_canonicalized_resource(self):
        return self.get_uri_path()

    def get_canonicalized_amz_headers(self, headers):
        result = ''
        headers = [(name.lower(), value) for name, value in headers.iteritems()
            if name.lower().startswith('x-amz-')]
        headers.sort()
        return ''.join('%s:%s\n' % (name, value) for name, value in headers)

    def get_signature(self, headers):
        text = self.verb + '\n'
        text += headers.get('Content-MD5', '') + '\n'
        text += headers.get('Content-Type', '') + '\n'
        text += headers.get('Date', '') + '\n'
        text += self.get_canonicalized_amz_headers(headers)
        text += self.get_canonicalized_resource()
        return self.service.sign(text)

    def submit(self):
        return self.get_page(url=self.get_uri(), method=self.verb,
                             postdata=self.data, headers=self.get_headers())

    def get_page(self, *a, **kw):
        return getPage(*a, **kw)


class S3(object):

    root_uri = 'https://s3.amazonaws.com/'
    request_factory = S3Request

    def __init__(self, service):
        self.service = service

    def make_request(self, *a, **kw):
        """
        Create a request with the arguments passed in.

        This uses the request_factory attribute, adding the service to the
        arguments passed in.
        """
        return self.request_factory(service=self.service, *a, **kw)

    def _parse_bucket_list(self, response):
        """
        Parse XML bucket list response.
        """
        root = XML(response)
        for bucket in root.find(name_space + 'Buckets'):
            timeText = bucket.findtext(name_space + 'CreationDate')
            yield {
                'name': bucket.findtext(name_space + 'Name'),
                'created': Time.fromISO8601TimeAndDate(timeText),
                }

    def list_buckets(self):
        """
        List all buckets.

        Returns a list of all the buckets owned by the authenticated sender of
        the request.
        """
        deferred = self.make_request('GET').submit()
        deferred.addCallback(self._parse_bucket_list)
        return deferred

    def create_bucket(self, bucket):
        """
        Create a new bucket.
        """
        return self.make_request('PUT', bucket).submit()

    def delete_bucket(self, bucket):
        """
        Delete a bucket.

        The bucket must be empty before it can be deleted.
        """
        return self.make_request('DELETE', bucket).submit()

    def put_object(self, bucket, object_name, data, content_type=None,
                   metadata={}):
        """
        Put an object in a bucket.

        Any existing object of the same name will be replaced.
        """
        return self.make_request('PUT', bucket, object_name, data,
                                 content_type, metadata).submit()

    def get_object(self, bucket, object_name):
        """
        Get an object from a bucket.
        """
        return self.make_request('GET', bucket, object_name).submit()

    def head_object(self, bucket, object_name):
        """
        Retrieve object metadata only.

        This is like get_object, but the object's content is not retrieved.
        Currently the metadata is not returned to the caller either, so this
        method is mostly useless, and only provided for completeness.
        """
        return self.make_request('HEAD', bucket, object_name).submit()

    def delete_object(self, bucket, object_name):
        """
        Delete an object from a bucket.

        Once deleted, there is no method to restore or undelete an object.
        """
        return self.make_request('DELETE', bucket, object_name).submit()
