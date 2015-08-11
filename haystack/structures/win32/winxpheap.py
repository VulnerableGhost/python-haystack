# -*- coding: utf-8 -*-
#


""" Win heap structure - from LGPL metasm
http://www.informit.com/articles/article.aspx?p=1081496

"""

__author__ = "Loic Jaquemet"
__copyright__ = "Copyright (C) 2012 Loic Jaquemet"
__license__ = "GPL"
__maintainer__ = "Loic Jaquemet"
__email__ = "loic.jaquemet+python@gmail.com"
__status__ = "Production"


import ctypes
import logging

from haystack import model
from haystack import listmodel
from haystack.abc import interfaces

from haystack import model
from haystack import utils
from haystack import constraints

from haystack.structures.win32 import winxp_32 as gen

import ctypes
import struct
import logging
import sys

import code

log = logging.getLogger('winxpheap')

############# Start methods overrides #################
# constraints are in constraints files

class WinXPHeapValidator(listmodel.ListModel):
    """
    this listmodel Validator will register know important list fields
    in the winxp HEAP,
    and be used to validate the loading of these structures.
    This class contains all helper functions used to parse the winxpheap structures.
    """

    def __init__(self, memory_handler, my_constraints, winxpheap_module):
        if not isinstance(memory_handler, interfaces.IMemoryHandler):
            raise TypeError("Feed me a IMemoryHandler")
        if not isinstance(my_constraints, interfaces.IModuleConstraints):
            raise TypeError("Feed me a IModuleConstraints")
        super(WinXPHeapValidator, self).__init__(memory_handler, my_constraints)
        self.winxpheap = winxpheap_module



def HEAP_SEGMENT_get_UCR_segment_list(self, mappings):
    """Returns a list of UCR segments for this segment.
    HEAP_SEGMENT.UCRSegmentList is a linked list to UCRs for this segment.
    Some may have Size == 0.
    """
    ucrs = list()
    for ucr in self.iterate_list_field(mappings, 'UCRSegmentList'):
        ucr_struct_addr = ucr._orig_address_
        ucr_addr = utils.get_pointee_address(ucr.Address)
        # UCR.Size are not chunks sizes. NOT *8
        log.debug("Segment.UCRSegmentList: 0x%0.8x addr: 0x%0.8x size: 0x%0.5x" % (
            ucr_struct_addr, ucr_addr, ucr.Size))
        ucrs.append(ucr)
    return ucrs

HEAP_SEGMENT.get_UCR_segment_list = HEAP_SEGMENT_get_UCR_segment_list

# HEAP

# HEAP CommitRoutine encoded by a global key
# The HEAP handle data structure includes a function pointer field called
# CommitRoutine that is called when memory regions within the heap are committed.
# Starting with Windows Vista, this field was encoded using a random value that
# was also stored as a field in the HEAP handle data structure.

HEAP.expectedValues = {
    'Signature': [0xeeffeeff],
    'FrontEndHeapType': [0, 1, 2], # I think that is only 0, 1 on winxp
    'CommitRoutine': constraints.IgnoreMember,
}

# TODO 2015-06 check, I thing segmentlist where 'segments' array in xp
HEAP._listHead_ = [#('SegmentList', HEAP_SEGMENT, 'SegmentListEntry', -16),
                   # maybe UCRsegments ???
                   #('UCRList', HEAP_UCR_DESCRIPTOR, 'ListEntry', 0),
                   # for get_freelists. offset is sizeof(HEAP_ENTRY)
                   #('FreeLists', HEAP_FREE_ENTRY, 'FreeList', -8),
                   ('VirtualAllocdBlocks', HEAP_VIRTUAL_ALLOC_ENTRY, 'Entry', -8)]
# HEAP.SegmentList. points to SEGMENT.SegmentListEntry.
# SEGMENT.SegmentListEntry. points to HEAP.SegmentList.
# you need to ignore the Head in the iterator...


def HEAP_get_virtual_allocated_blocks_list(self, mappings):
    """Returns a list of virtual allocated entries.

    TODO: need some working on.
    """
    vallocs = list()
    for valloc in self.iterate_list_field(mappings, 'VirtualAllocdBlocks'):
        vallocs.append(valloc)
        log.debug("vallocBlock: @0x%0.8x commit: 0x%x reserved: 0x%x" % (
            valloc._orig_address_, valloc.CommitSize, valloc.ReserveSize))
    return vallocs

HEAP.get_virtual_allocated_blocks_list = HEAP_get_virtual_allocated_blocks_list


def HEAP_get_free_UCR_segment_list(self, mappings):
    """Returns a list of available UCR segments for this heap.
    HEAP.UCRList is a linked list to all UCRSegments

    """
    # TODO: exclude UCR segment from valid pointer values in _memory_handler.
    ucrs = list()
    for ucr in self.iterate_list_field(mappings, 'UCRList'):
        ucr_struct_addr = ucr._orig_address_
        ucr_addr = utils.get_pointee_address(ucr.Address)
        # UCR.Size are not chunks sizes. NOT *8
        log.debug("Heap.UCRList: 0x%0.8x addr: 0x%0.8x size: 0x%0.5x" % (
            ucr_struct_addr, ucr_addr, ucr.Size))
        ucrs.append(ucr)
    return ucrs

HEAP.get_free_UCR_segment_list = HEAP_get_free_UCR_segment_list


# 2015-06-30 modified for windows xp
#('Segments', POINTER_T(struct__HEAP_SEGMENT) * 64),
def HEAP_get_segment_list(self, mappings):
    """returns a list of all segment attached to one Heap structure."""
    segments = list()
    segments_addr = utils.get_pointee_address(self.SegmentList)
    m = mappings.get_mapping_for_address(segments_addr)
    st = m.read_struct(segments_addr, (struct__HEAP_SEGMENT*64))
    base_addr = st._orig_address_
    size_segment = ctypes.sizeof(struct__HEAP_SEGMENT)
    for i, segment in enumerate(st):
        segment_addr = segment._orig_address_+(i*size_segment)
        first_addr = utils.get_pointee_address(segment.FirstEntry)
        last_addr = utils.get_pointee_address(segment.LastValidEntry)
        log.debug(
            'Heap.Segment: 0x%0.8x FirstEntry: 0x%0.8x LastValidEntry: 0x%0.8x' %
            (segment_addr, first_addr, last_addr))
        segments.append(segment)
    return segments


HEAP.get_segment_list = HEAP_get_segment_list


def HEAP_get_chunks(self, mappings):
    """Returns a list of tuple(address,size) for all chunks in
     the backend allocator."""
    allocated = list()
    free = list()
    for segment in self.get_segment_list(mappings):
        first_addr = utils.get_pointee_address(segment.FirstEntry)
        last_addr = utils.get_pointee_address(segment.LastValidEntry)
        # create the skip list for each segment.
        skiplist = dict()
        for ucr in segment.get_UCR_segment_list(mappings):
            ucr_addr = utils.get_pointee_address(ucr.Address)
            # UCR.Size are not chunks sizes. NOT *8
            skiplist[ucr_addr] = ucr.Size
        #
        chunk_addr = first_addr
        while (chunk_addr < last_addr):
            if chunk_addr in skiplist:
                size = skiplist[chunk_addr]
                log.debug(
                    'Skipping 0x%0.8x - skip %0.5x bytes to 0x%0.8x' %
                    (chunk_addr, size, chunk_addr + size))
                chunk_addr += size
                continue
            chunk_header = mappings.getRef(HEAP_ENTRY, chunk_addr)
            if chunk_header is None:  # force read it
                chunk_header = _get_chunk(mappings, self, chunk_addr)
            if self.EncodeFlagMask:  # heap.EncodeFlagMask
                chunk_header = HEAP_ENTRY_decode(chunk_header, self)
            #log.debug('\t\tEntry: 0x%0.8x\n%s'%( chunk_addr, chunk_header))

            if ((chunk_header.Flags & 1) == 1):
                log.debug(
                    'Chunk 0x%0.8x is in use size: %0.5x' %
                    (chunk_addr, chunk_header.Size * 8))
                allocated.append((chunk_addr, chunk_header.Size * 8))
            else:
                log.debug('Chunk 0x%0.8x is FREE' % (chunk_addr))
                free.append((chunk_addr, chunk_header.Size * 8))
                pass
            chunk_addr += chunk_header.Size * 8
    return (allocated, free)

HEAP.get_chunks = HEAP_get_chunks


def HEAP_get_frontend_chunks(self, mappings):
    """ windows xp ?
        the list of chunks from the frontend are deleted from the segment chunk list.

        Functionnaly, (page 28) LFH_HEAP should be fetched by HEAP_BUCKET calcul

    //position 0x7 in the header denotes
    //whether the chunk was allocated via
    //the front-end or the back-end (non-encoded ;) )
    if(ChunkHeader->UnusedBytes & 0x80)
        RtlpLowFragHeapFree
    else
        BackEndHeapFree

    """
    res = list()
    all_free = list()
    all_committed = list()
    log.debug('HEAP_get_frontend_chunks')
    ptr = self.FrontEndHeap
    addr = utils.get_pointee_address(ptr)
    if self.FrontEndHeapType == 1:  # windows XP per default
        # TODO delete this ptr from the heap-segment entries chunks
        for x in range(128):
            log.debug('finding lookaside %d at @%x' % (x, addr))
            m = mappings.get_mapping_for_address(addr)
            st = m.read_struct(addr, HEAP_LOOKASIDE)
            # load members on self.FrontEndHeap car c'est un void *
            for free in st.iterateList('ListHead'):  # single link list.
                # TODO delete this free from the heap-segment entries chunks
                log.debug('free')
                res.append(free)  # ???
                pass
            addr += ctypes.sizeof(HEAP_LOOKASIDE)
    elif self.FrontEndHeapType == 2:  # win7 per default
        log.debug('finding frontend at @%x' % (addr))
        m = mappings.get_mapping_for_address(addr)
        st = m.read_struct(addr, LFH_HEAP)
        # LFH is a big chunk allocated by the backend allocator, called subsegment
        # but rechopped as small chunks of a heapbin.
        # Active subsegment hold that big chunk.
        #
        #
        # load members on self.FrontEndHeap car c'est un void *
        if not st.load_members(mappings, 1):
            log.error('Error on loading frontend')
            raise model.NotValid('Frontend load at @%x is not valid' % (addr))

        # log.debug(st.LocalData[0].toString())
        #
        # 128 HEAP_LOCAL_SEGMENT_INFO
        for sinfo in st.LocalData[0].SegmentInfo:
            # TODO , what about ActiveSubsegment ?
            for items_ptr in sinfo.CachedItems:  # 16 caches items max
                items_addr = utils.get_pointee_address(items_ptr)
                if not bool(items_addr):
                    #log.debug('NULL pointer items')
                    continue
                m = mappings.get_mapping_for_address(items_addr)
                subsegment = m.read_struct(items_addr, HEAP_SUBSEGMENT)
                # log.debug(subsegment)
                # TODO current subsegment.SFreeListEntry is on error at some depth.
                # bad pointer value on the second subsegment
                chunks = subsegment.get_userblocks()
                free = subsegment.get_freeblocks()
                committed = set(chunks) - set(free)
                all_free.extend(free)
                all_committed.extend(committed)
                log.debug(
                    'subseg: 0x%0.8x, commit: %d chunks free: %d chunks' %
                    (items_addr, len(committed), len(free)))
    else:
        # print 'FrontEndHeapType == %d'%(self.FrontEndHeapType)
        #raise StopIteration
        pass
    return all_committed, all_free

HEAP.get_frontend_chunks = HEAP_get_frontend_chunks

# HEAP_SUBSEGMENT


def HEAP_SUBSEGMENT_get_userblocks(self):
    """
    AggregateExchg contains info on userblocks, number left, depth
    """
    userblocks_addr = utils.get_pointee_address(self.UserBlocks)
    if not bool(userblocks_addr):
        log.debug('Userblocks is null')
        return []
    # the structure is astructure in an unnamed union of self
    st = self._3._0
    # its basically an array of self.BlockCount blocks of self.BlockSize*8
    # bytes.
    log.debug(
        'fetching %d blocks of %d bytes' %
        (st.BlockCount, st.BlockSize * 8))
    # UserBlocks points to HEAP_USERDATA_HEADER. Real user data blocks will starts after sizeof( HEAP_USERDATA_HEADER ) = 0x10
    # each chunk starts with a 8 byte header + n user-writeable data
    # user writable chunk starts with 2 bytes for next offset
    # basically, first committed block is first.
    # ( page 38 )
    userblocks = [
        (userblocks_addr +
         0x10 +
         st.BlockSize *
         8 *
         i,
         st.BlockSize *
         8) for i in range(
            st.BlockCount)]
    #
    # we need to substract non allocated blocks
    # self.AggregateExchg.Depth counts how many blocks are remaining free
    # if self.AggregateExchg.FreeEntryOffset == 0x2, there a are no commited
    # blocks
    return userblocks


HEAP_SUBSEGMENT.get_userblocks = HEAP_SUBSEGMENT_get_userblocks


def HEAP_SUBSEGMENT_get_freeblocks(self):
    """
    Use AggregateExchg.Depth and NextFreeoffset to fetch the head, then traverse the links
    """
    userblocks_addr = utils.get_pointee_address(self.UserBlocks)
    if not bool(userblocks_addr):
        return []
    # structure is in a structure in an union
    # struct_c__S__INTERLOCK_SEQ_Ua_Sa_0
    aggExchange = self.AggregateExchg._0._0
    if aggExchange.FreeEntryOffset == 0x2:
        log.debug(' * FirstFreeOffset==0x2 Depth==%d' % (aggExchange.Depth))
    # self.AggregateExchg.Depth the size of UserBlock divided by the HeapBucket size
    # self.AggregateExchg.FreeEntryOffset starts at 0x2 (blocks), which means 0x10 bytes after UserBlocks
    # see Understanding LFH page 14
    # nextoffset of user data is at current + offset*8 + len(HEAP_ENTRY)
    # the structure is astructure in an unnamed union of self
    st = self._3._0
    freeblocks = [(userblocks_addr +
                   (aggExchange.FreeEntryOffset *
                    8) +
                   st.BlockSize *
                   8 *
                   i, st.BlockSize *
                   8) for i in range(aggExchange.Depth)]
    return freeblocks
    ###

    #ptr = utils.get_pointee_address(self.AggregateExchg.FreeEntryOffset)
    # for i in range(self.AggregateExchg.Depth):
    #    free.append( userBlocks+ 8*ptr)
    #    ## ptr = m.readWord( userBlocks+ 8*ptr+8 ) ?????
    # return blocks

    #free = []
    #ptr = subseg.FreeEntryOffset
    # subseg.depth.times {
    #    free << (up + 8*ptr)
    #    ptr = @dbg.memory[up + 8*ptr + 8, 2].unpack('v')[0]
    #}
    #@foo ||= 0
    #@foo += 1
    #p @foo if @foo % 10 == 0#
    #
    #up += 0x10
    #list -= free
    # list.each { |p| @chunks[p+8] = bs*8 - (@cp.decode_c_struct('HEAP_ENTRY', @dbg.memory, p).unusedbytes & 0x7f) }
    # end

HEAP_SUBSEGMENT.get_freeblocks = HEAP_SUBSEGMENT_get_freeblocks

# HEAP_UCR_DESCRIPTOR
#HEAP_UCR_DESCRIPTOR._listMember_ = ['ListEntry']
#HEAP_UCR_DESCRIPTOR._listHead_ = [    ('SegmentEntry', HEAP_SEGMENT, 'SegmentListEntry'),    ]

# per definition, reserved space is not maped.
#HEAP_UCR_DESCRIPTOR.expectedValues = {
#    'Address': constraints.IgnoreMember,
#}

# HEAP_LOCAL_SEGMENT_INFO
# HEAP_LOCAL_SEGMENT_INFO.LocalData should be a pointer, but the values are small ints ?
# HEAP_LOCAL_SEGMENT_INFO.LocalData == 0x3 ?
#HEAP_LOCAL_SEGMENT_INFO.expectedValues = {
#    'LocalData': constraints.IgnoreMember,
#}


# TODO current subsegment.SFreeListEntry is on error at some depth.
# bad pointer value on the second subsegment
HEAP_SUBSEGMENT.expectedValues = {
    'SFreeListEntry': constraints.IgnoreMember,
}


def HEAP_getFreeLists_by_blocksindex(self, mappings):
    """ Understanding_the_LFH.pdf page 21
    Not Implemented yet
    """
    freeList = []
    # 128 blocks
    start = ctypes.addressof(self.BlocksIndex)
    bi_addr = utils.get_pointee_address(self.BlocksIndex)
    # enumerate BlocksIndex recursively on ExtendedLookup param
    while bi_addr != 0:
        log.debug('BLocksIndex is at %x' % (bi_addr))
        m = mappings.get_mapping_for_address(bi_addr)
        bi = m.read_struct(bi_addr, HEAP_LIST_LOOKUP)
        """
            ('ExtendedLookup', POINTER(HEAP_LIST_LOOKUP)),
            ('ArraySize', __uint32_t),
            ('ExtraItem', __uint32_t),
            ('ItemCount', __uint32_t),
            ('OutOfRangeItems', __uint32_t),
            ('BaseIndex', __uint32_t),
            ('ListHead', POINTER(LIST_ENTRY)),
            ('ListsInUseUlong', POINTER(__uint32_t)),
            ('ListHints', POINTER(POINTER(LIST_ENTRY))),
        """
        log.debug('ArraySize is %d' % (bi.ArraySize))
        log.debug('BlocksIndex: %s' % (bi.toString()))
        hints_addr = utils.get_pointee_address(bi.ListHints)
        log.debug('ListHints is pointing to %x' % (hints_addr))
        extlookup_addr = utils.get_pointee_address(bi.ExtendedLookup)
        log.debug('ExtendedLookup is pointing to %x' % (extlookup_addr))
        if extlookup_addr == 0:
            """ all chunks of size greater than or equal to BlocksIndex->ArraySize - 1 will
            be stored in ascending order in FreeList[ArraySize-BaseIndex – 1] """
            log.debug(
                'Free chunks >= %d stored at FreeList[ArraySize(%d)-BaseIndex(%d) – 1]' %
                (bi.ArraySize - 1, bi.ArraySize, bi.BaseIndex))
            #raise NotImplementedError()
        log.debug('-' * 80)
        bi_addr = extlookup_addr
    #
    raise NotImplementedError('NOT FINISHED')
    #raise StopIteration


def HEAP_ENTRY_decode(chunk_header, heap):
    """returns a decoded copy """
    # contains the Size
    # 32 bits: struct__HEAP_ENTRY_0_0
    # FIXME BUG, we need to use _0_0_0_0 for 64 bits, otherwise
    # we are reading bad data
    # 64 bits: struct__HEAP_ENTRY_0_0_0_0
    chunk_len = ctypes.sizeof(struct__HEAP_ENTRY_0_0)
    chunk_header_decoded = (
        struct__HEAP_ENTRY_0_0).from_buffer_copy(chunk_header)
    # decode the heap entry chunk header with the heap.Encoding
    working_array = (
        ctypes.c_ubyte *
        chunk_len).from_buffer(chunk_header_decoded)
    encoding_array = (
        ctypes.c_ubyte *
        chunk_len).from_buffer_copy(
        heap.Encoding)
    # check if (heap.Encoding & working_array)
    s = 0
    for i in range(chunk_len):
        s += working_array[i] & encoding_array[i]
    # if s == 0: #DEBUG TODO
    #    print 'NOT ENCODED !!!',hex(ctypes.addressof(heap))
    #    return chunk_header
    for i in range(chunk_len):
        working_array[i] ^= encoding_array[i]
    return chunk_header_decoded

# imported dynamically
# pylint: disable=undefined-variable
HEAP_ENTRY.decode = HEAP_ENTRY_decode


def _get_chunk(mappings, heap, entry_addr):
    m = mappings.get_mapping_for_address(entry_addr)
    chunk_header = m.read_struct(entry_addr, HEAP_ENTRY)
    mappings.keepRef(chunk_header, HEAP_ENTRY, entry_addr)
    chunk_header._orig_address_ = entry_addr
    return chunk_header


# 2015-06-30 for winXP
#     ('FreeLists', struct__LIST_ENTRY * 128),
def HEAP_get_freelists(self, mappings):
    """Returns the list of free chunks.

    This method is very important because its used by memory_mappings to
    load _memory_handler that contains subsegment of a heap.

    Understanding_the_LFH.pdf page 18 ++
    We iterate on HEAP.FreeLists to get ALL free blocks.

    @returns freeblock_addr : the address of the HEAP_ENTRY (chunk header)
        size : the size of the free chunk + HEAP_ENTRY header size, in blocks.
    """
    # FIXME: we should use get_segmentlist to coallescce segment in one heap
    # memory mapping. Not free chunks.
    res = list()
    # todo iterate on the 128 list_entry, which are pointing to HEAP_ENTRY
    # FIXME
    return res
    for freeblock in self.iterate_list_field(mappings, 'FreeLists'):
        if self.EncodeFlagMask:
            chunk_header = HEAP_ENTRY_decode(freeblock, self)
        # size = header + freespace
        res.append((freeblock._orig_address_, chunk_header.Size * 8))
    return res

# imported dynamically
# pylint: disable=undefined-variable
HEAP.get_freelists = HEAP_get_freelists

# def HEAP_getFreeListsWinXP(self, _memory_handler):
# Understanding_the_LFH.pdf page 17 """


# LIST_ENTRY
from haystack import listmodel
listmodel.declare_double_linked_list_type(LIST_ENTRY, 'Flink', 'Blink')