#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
"""
  Extension for list grammars.
  
"""
__author__ = "Loic Jaquemet"
__copyright__ = "Copyright (C) 2012 Loic Jaquemet"
__license__ = "GPL"
__maintainer__ = "Loic Jaquemet"
__email__ = "loic.jaquemet+python@gmail.com"
__status__ = "Beta"


''' insure ctypes basic types are subverted '''
from haystack import utils

import ctypes
import logging

log=logging.getLogger('listmodel')

class ListModel(object):
  _listMember_=[] # members that are the 2xpointer of same type linl
  _listHead_=[] # head structure of a linkedlist

  def loadListOfType(self, fieldname, mappings, structType, listFieldname, maxDepth):
    ''' load self.fieldname as a list of structType '''
    listfield = getattr(structType, listFieldname)
    offset = 0 - listfield.offset - listfield.size 
    return self._loadListEntries(fieldname, mappings,  structType, maxDepth, offset)


  def loadListEntries(self, fieldname, mappings, maxDepth):
    ''' load self.fieldname as a list of self-typed '''
    listfield = getattr(type(self), fieldname)
    offset = 0 - listfield.offset - listfield.size 
    return self._loadListEntries(fieldname, mappings, self.__class__ , maxDepth, offset)
    

  def _loadListEntries(self, fieldname, mappings,  structType, maxDepth, offset):
    ''' 
    we need to load the pointed entry as a valid struct at the right offset, 
    and parse it.
    '''
    head = getattr(self, fieldname)
    flink = utils.getaddress(head.FLink) 
    blink = utils.getaddress(head.BLink) 
    #print '--Listentry %s.%s 0x%x/0x%x 0x%x/0x%x with offset %d'%(structType.__name__, 
    #  fieldname, flink+offset, flink, blink+offset, blink, offset)
    if flink == blink:
      log.debug('Load LIST_ENTRY on %s, only 1 element'%(fieldname))

    # load both links// both ways, BLink is expected to be loaded from cache
    for link, name in [(flink, 'FLink'), (blink, 'BLink')]:
      if not bool(link):
        log.warning('%s has a Null pointer %s - NOT loading'%(fieldname, name))
        continue

      link = link+offset
      # validation of pointer values already have been made in isValid

      # use cache if possible, avoid loops.
      #XXX 
      from haystack import model
      ref = model.getRef( structType, link)
      if ref: # struct has already been loaded, bail out
        log.debug("%s.%s loading from references cache %s/0x%lx"%(fieldname, name, structType, link ))
        continue # goto Blink or finish
      else:
        #  OFFSET read, specific to a LIST ENTRY model
        memoryMap = utils.is_valid_address_value( link, mappings, structType)
        st = memoryMap.readStruct( link, structType) # point at the right offset
        model.keepRef(st, structType, link)
  
        ##print st
  
        # load the list entry structure members
        if not st.loadMembers(mappings, maxDepth-1):
          raise ValueError
    
    return True


  def _isLoadableMemberList(self, attr, attrname, attrtype):
    '''
      Check if the member is loadable.
      A c_void_p cannot be load generically, You have to take care of that.
    '''
    if not super(ListModel, self)._isLoadableMemberList(attr, attrname, attrtype) :
      return False
    if attrname in self._listMember_:
      return False
    return True
    
  def loadMembers(self,mappings, maxDepth):
    ''' 
    load basic types members, 
    then load list elements members recursively,
    then load list head elements members recursively.
    '''
    log.debug('load list elements at 0x%x'%(ctypes.addressof(self)))
    if not super(ListModel, self).loadMembers(mappings, maxDepth):
      return False

    log.debug('load list elements members recursively on %s'%(type(self).__name__))
    log.debug( 'listmember %s'%self.__class__._listMember_)
    for fieldname in self._listMember_:
      self.loadListEntries(fieldname, mappings, maxDepth )

    log.debug('load list head elements members recursively on %s'%(type(self).__name__))
    for fieldname,structType,structFieldname in self._listHead_:
      self.loadListOfType(fieldname, mappings, 
                          structType, structFieldname, maxDepth ) 
   
    return True

  def getFieldIterator(self, mappings, fieldname):
    if fieldname not in self._listMember_:
      raise ValueError('No such listMember field ')
    
    listfield = getattr(type(self), fieldname)
    offset = 0 - listfield.offset - listfield.size 
    
    done = []
    obj = self
    link = getattr(obj, fieldname).FLink # XXX
    while link not in done:

      done.append(link)

      if not bool(link):
        log.warning('%s has a Null pointer %s - NOT loading'%(fieldname, name))
        raise StopIteration

      link = link+offset
      # use cache if possible, avoid loops.
      from haystack import model
      st = model.getRef( structType, link)
      if st: # struct has already been loaded, bail out
        log.debug("%s.%s loading from references cache %s/0x%lx"%(fieldname, name, structType, link ))
        yield st
      else:
        #  OFFSET read, specific to a LIST ENTRY model
        memoryMap = utils.is_valid_address_value( link, mappings, structType)
        st = memoryMap.readStruct( link, structType) # point at the right offset
        model.keepRef(st, structType, link)
        yield st
      #
      link = getattr(st, fieldname).FLink # XXX

    raise StopIteration

  def getListEntryIterator(self):
    ''' returns [(fieldname, iterator), .. ] '''
    for fieldname in self._listMember_:
      yield (fieldname, self.getFieldIterator(mappings, fieldname ) )
  

def declare_double_linked_list_type( structType, forward, backward):
  ''' declare a double linked list type.
  '''
  # test existence
  flinkType = getattr(structType, forward) 
  blinkType = getattr(structType, backward)
  d = dict(structType.getFields())
  flinkType = d[forward]
  blinkType = d[backward]
  if not utils.isPointerType(flinkType):
    raise TypeError('The %s field is not a pointer.'%(forward))
  if not utils.isPointerType(blinkType):
    raise TypeError('The %s field is not a pointer.'%(backward))

  def iterateList(self, mappings):
    ''' iterate forward, then backward, until null or duplicate '''    
    done = [0]
    obj = self
    for fieldname in [forward, backward]:
      link = getattr(obj, fieldname)
      addr = utils.getaddress(link)
      log.debug('iterateList got a %s/%s'%(link,addr))
      while addr not in done:
        done.append(addr)
        memoryMap = utils.is_valid_address_value( addr, mappings, structType)
        if memoryMap == False:
          raise ValueError('the link of this linked list has a bad value')
        st = memoryMap.readStruct( addr, structType)
        yield st
        # next
        link = getattr(st, fieldname)
        addr = utils.getaddress(link)

    raise StopIteration
  
  # set iterator on the list structure
  structType.iterateList = iterateList
  log.debug('%s has beed fitted with a list iterator self.iterateList(mappings)'%(structType))
  return
    
